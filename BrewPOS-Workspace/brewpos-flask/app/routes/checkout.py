import random
import math
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import db
from app.models.customer import Customer, GUEST_NICKNAME
from app.models.transaction import Transaction, TransactionItem
from app.models.menu import Menu
from app.models.reward import Reward
from app.models.system_settings import SystemSettings, get_setting_float, get_setting_int
from app.models.shift import Shift
from app.models.historical_sales import HistoricalSales
from app.services.system_logger import log_activity
from app.services.gamification_service import process_gamification_async
from app.services.inventory_service import deduct_ingredients_for_order, restore_ingredients_for_void
from app.services.period_lock import assert_period_open, PeriodLockedError
from app.routes.shift import find_shift_at
from app.middleware.auth import get_current_user_id, is_supervisor

checkout_bp = Blueprint('checkout', __name__, url_prefix='/api/checkout')


def _current_cashier_id():
    user_id = get_current_user_id()
    return int(user_id) if user_id else None


def _get_open_shift():
    """Sesi kas milik toko; dipakai bersama semua kasir yang sedang login."""
    return Shift.query.filter(Shift.status.in_(['OPEN', 'NEEDS_REVIEW'])) \
                      .order_by(Shift.startTime.desc()).first()


def parse_waktu(teks):
    """
    String ISO -> datetime naif.

    Naif, bukan tz-aware: seluruh aplikasi menyimpan waktu naif UTC, dan
    mencampur keduanya membuat pembandingan tanggal melempar TypeError di
    tempat-tempat yang jauh dari sini.
    """
    if not teks:
        return None
    try:
        hasil = datetime.fromisoformat(str(teks).replace('Z', '+00:00'))
    except ValueError:
        return None
    return hasil.replace(tzinfo=None) if hasil.tzinfo else hasil


def next_transaction_code(waktu):
    """
    Nomor struk: TR + yyyymmdd + urutan 6 digit dalam hari itu.

    Memakai urutan tertinggi + 1, bukan count(). Dengan count(), menyisipkan
    transaksi ke hari lampau menghasilkan nomor yang sudah terpakai -- dan tidak
    ada unique constraint di transactionCode yang akan menangkapnya.
    """
    awalan = f"TR{waktu.strftime('%Y%m%d')}"
    terpakai = [
        row[0] for row in db.session.query(Transaction.transactionCode)
        .filter(Transaction.transactionCode.like(f"{awalan}%")).all()
        if row[0]
    ]
    tertinggi = 0
    for kode in terpakai:
        ekor = kode[len(awalan):]
        if ekor.isdigit():
            tertinggi = max(tertinggi, int(ekor))
    return f"{awalan}{tertinggi + 1:06d}"


def _resolve_transaction_time(data, supervisor):
    """
    Tanggal transaksi kalau diinput mundur. -> (waktu | None, error | None)

    None berarti transaksi biasa (waktu sekarang). Semua penolakan di sini
    sengaja terjadi sebelum apa pun ditulis.
    """
    waktu = parse_waktu(data.get('createdAt'))
    if waktu is None:
        if data.get('createdAt'):
            return None, ('Tanggal transaksi tidak terbaca', 400)
        return None, None

    sekarang = datetime.utcnow()
    # Selisih semenit dianggap "sekarang": jam klien bisa meleset sedikit, dan
    # itu tidak perlu diperlakukan sebagai input mundur.
    if abs((sekarang - waktu).total_seconds()) < 60:
        return None, None

    if waktu > sekarang:
        return None, ('Tanggal transaksi belum terjadi', 400)
    if not supervisor:
        return None, ('Input transaksi bertanggal mundur memerlukan Head Barista atau di atasnya', 403)

    # Hari itu sudah punya baris omzet lama; menambah transaksi berrincian di
    # tanggal yang sama berarti omzetnya terhitung dua kali di laporan.
    if HistoricalSales.query.filter_by(date=waktu.date()).first():
        return None, (
            f'Tanggal {waktu.date().isoformat()} sudah punya catatan omzet lama. '
            'Hapus dulu baris omzet harian itu kalau mau dirinci per transaksi.', 409)

    return waktu, None


def _get_or_create_guest():
    """Satu baris Guest untuk semua transaksi non-member; tidak ikut program loyalty."""
    guest = Customer.query.filter_by(nickname=GUEST_NICKNAME).first()
    if not guest:
        guest = Customer(nickname=GUEST_NICKNAME, points=0, xp=0, level=1, streakCount=0)
        db.session.add(guest)
        db.session.flush()
    return guest


def _is_guest(customer):
    return bool(customer) and customer.nickname == GUEST_NICKNAME


def _resolve_customer(customer_id, nickname):
    """
    Member diidentifikasi lewat id. Tidak ada lagi pembuatan member otomatis di sini:
    member wajib punya no. HP atau email, dan itu hanya bisa dijamin lewat pendaftaran.
    Returns (customer, error) dengan error = (message, status_code).
    """
    if customer_id:
        customer = Customer.query.get(int(customer_id))
        if not customer:
            return None, ('Member tidak ditemukan. Daftarkan member lebih dulu.', 404)
        return customer, None

    if not nickname or nickname == GUEST_NICKNAME:
        return _get_or_create_guest(), None

    customer = Customer.query.filter_by(nickname=nickname).first()
    if not customer:
        return None, (
            f'Member "{nickname}" belum terdaftar. Daftarkan dulu dengan no. HP atau email.',
            404
        )
    return customer, None


def _resolve_line_items(items, customer, supervisor):
    """
    Rebuild the order from database prices. Client-sent prices are ignored entirely.

    Item discounts are honoured only when backed by the employee's remaining daily quota
    (counted in cups) or authorised by a HEADBAR+ user. Otherwise they are dropped, so a
    tampered payload cannot zero out an order.

    Returns (tx_items_data, gross_total, quota_used, error), where error is
    (message, status_code) or None.
    """
    menu_ids = []
    for it in items:
        raw = it.get('menuId')
        try:
            menu_ids.append(int(raw))
        except (TypeError, ValueError):
            return None, 0, 0, (f'Invalid menu id: {raw}', 400)

    menus = {m.id: m for m in Menu.query.filter(Menu.id.in_(menu_ids)).all()} if menu_ids else {}

    free_slots = 0
    if customer and customer.customerType == 'EMPLOYEE':
        free_slots = max(0, (customer.dailyQuota or 0) - (customer.usedQuotaToday or 0))

    tx_items_data = []
    gross_total = 0
    quota_used = 0

    for it, m_id in zip(items, menu_ids):
        try:
            qty = int(it.get('quantity', 1))
        except (TypeError, ValueError):
            return None, 0, 0, (f'Invalid quantity for menu item {m_id}', 400)

        if qty <= 0:
            return None, 0, 0, (f'Invalid quantity {qty} for menu item {m_id}', 400)

        menu_obj = menus.get(m_id)
        if not menu_obj:
            return None, 0, 0, (f'Menu item {m_id} not found', 404)

        actual_price = menu_obj.price
        try:
            item_disc = max(0, int(it.get('discountAmount', 0)))
        except (TypeError, ValueError):
            item_disc = 0
        item_disc = min(item_disc, actual_price)

        if item_disc > 0:
            covered_by_quota = (item_disc == actual_price and free_slots >= qty)
            if covered_by_quota:
                free_slots -= qty
                quota_used += qty
            elif not supervisor:
                # Cashier waiving price without quota backing: refuse the discount
                item_disc = 0

        gross_total += (actual_price - item_disc) * qty

        tx_items_data.append({
            'menuId': m_id,
            'quantity': qty,
            'price': actual_price,
            'discountAmount': item_disc,
            'hpp': menu_obj.hpp
        })

    return tx_items_data, gross_total, quota_used, None


def _resolve_order_discount(reward, requested_discount, gross_total, supervisor):
    """
    Order-level discount, decided server-side.

    A redeemed reward dictates its own rupiah value; the amount in the request body is
    ignored. A manual discount without a reward needs HEADBAR+ authorisation.

    Returns (order_discount, error) where error is (message, status_code) or None.
    """
    if reward:
        return min(max(0, reward.discountValue or 0), gross_total), None

    try:
        requested_discount = int(requested_discount or 0)
    except (TypeError, ValueError):
        requested_discount = 0

    if requested_discount <= 0:
        return 0, None

    if not supervisor:
        return 0, ('Diskon manual memerlukan otorisasi Head Barista atau di atasnya', 403)

    return min(requested_discount, gross_total), None

@checkout_bp.route('/history', methods=['GET'])
def get_history():
    try:
        # Muat rincian, menu, dan member sekaligus: to_dict() menyusuri
        # ketiganya, dan tanpa ini 50 struk terakhir jadi ratusan query kecil.
        transactions = Transaction.query.options(
            selectinload(Transaction.items).joinedload(TransactionItem.menu),
            joinedload(Transaction.customer),
        ).order_by(Transaction.createdAt.desc()).limit(50).all()
        return jsonify([t.to_dict(include_items=True, include_customer=True) for t in transactions])
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        print(f"Error fetching history: {e}")
        return jsonify({'error': 'Failed to fetch history'}), 500


@checkout_bp.route('', methods=['POST'])
def checkout():
    data = request.get_json() or {}
    customer_id = data.get('customerId')
    nickname = data.get('nickname')
    items = data.get('items', [])
    reward_id = data.get('rewardId')
    payment_method = data.get('paymentMethod', 'CASH')
    discount_amount = data.get('discountAmount', 0)  # parsed & authorised server-side below

    if not items:
        return jsonify({'error': 'Order items cannot be empty'}), 400

    try:
        supervisor = is_supervisor()

        # --- Input mundur -------------------------------------------------
        # Transaksi lama yang terlewat diinput. Dipisahkan sejak awal karena
        # hampir setiap keputusan di bawah berubah: sesi kas, kuota, stok, dan
        # undian poin.
        waktu, backdate_err = _resolve_transaction_time(data, supervisor)
        if backdate_err:
            return jsonify({'error': backdate_err[0]}), backdate_err[1]
        is_backdated = waktu is not None
        now = waktu or datetime.utcnow()
        assert_period_open(now)

        if is_backdated:
            # Sesi kas hari ini tidak boleh kecipratan uang kemarin: kalau ikut,
            # expectedEndingCash laci hari ini menggelembung dan memunculkan
            # selisih kas palsu.
            shift = find_shift_at(now)
            shift_id = shift.id if shift else None
            if shift and shift.status == 'CLOSED':
                # Lacinya sudah dihitung dan ditutup. Menulis ulang angkanya
                # diam-diam justru menyembunyikan ketidakcocokan dari manusia;
                # lebih baik ditandai supaya ada yang memeriksa.
                shift.status = 'NEEDS_REVIEW'
                catatan = f"Transaksi mundur ditambahkan {datetime.utcnow():%Y-%m-%d %H:%M}, kas perlu dicek ulang"
                shift.closingNote = f"{shift.closingNote}\n{catatan}" if shift.closingNote else catatan
        else:
            # Sesi kas ditentukan server dari sesi toko yang terbuka; kiriman klien
            # tidak dipercaya karena satu laci bisa dipakai beberapa kasir.
            open_shift = _get_open_shift()
            shift_id = open_shift.id if open_shift else None
        cashier_id = _current_cashier_id()

        # The customer must be resolved first: their remaining employee quota is what
        # authorises any item-level discount below.
        customer, err = _resolve_customer(customer_id, nickname)
        if err:
            return jsonify({'error': err[0]}), err[1]
        nickname = customer.nickname
        # Kuota karyawan adalah jatah "hari ini". Pada input mundur, menyentuhnya
        # berarti memakan jatah hari ini untuk minuman kemarin.
        if not is_backdated:
            customer.check_and_reset_quota()

        # Validate the redeemed reward before pricing, since it sets the order discount
        reward = None
        points_to_deduct = 0
        if reward_id:
            reward = Reward.query.get(int(reward_id))
            if not reward or not reward.active:
                return jsonify({'error': 'Reward not available or inactive'}), 400
            if not customer or customer.points < reward.pointsRequired:
                return jsonify({'error': 'Insufficient points to redeem this reward'}), 400
            points_to_deduct = reward.pointsRequired

        # [SECURITY]: Recalculate every line from database prices to prevent tampering
        tx_items_data, gross_total, employee_quota_used, err = _resolve_line_items(
            items, customer, supervisor
        )
        if err:
            return jsonify({'error': err[0]}), err[1]

        discount_amount, err = _resolve_order_discount(
            reward, discount_amount, gross_total, supervisor
        )
        if err:
            return jsonify({'error': err[0]}), err[1]

        total_amount = max(0, gross_total - discount_amount)

        # Calculate points & XP: 1 pt + 1 XP per Rp 1.000
        points_earned = math.floor(total_amount / 1000)
        is_lucky_drop = False
        bonus_points = 0

        is_guest = _is_guest(customer)

        # 20% Chance for Lucky Drop
        # Tidak berlaku untuk input mundur: hadiah acak pada entri ulang tidak
        # bisa diaudit, dan siapa pun yang boleh input mundur jadi bisa
        # mengulang input sampai undiannya keluar.
        if random.random() < 0.20 and not is_guest and not is_backdated:
            is_lucky_drop = True
            bonus_points = 50
            points_earned += bonus_points

        if is_guest:
            points_earned = 0
            is_lucky_drop = False
            bonus_points = 0

        new_points = max(0, customer.points + points_earned - points_to_deduct)
        new_xp = customer.xp + points_earned
        new_level = math.floor(new_xp / 100) + 1

        # Point Expiration Settings
        exp_days = get_setting_int('POINT_EXPIRATION_DAYS', 90)
        expiry_date = now + timedelta(days=exp_days)

        # Streak calculation
        new_streak = customer.streakCount or 0
        if customer.lastVisitDate:
            last_visit = customer.lastVisitDate.date()
            today = now.date()
            diff_days = (today - last_visit).days
            if diff_days == 1:
                new_streak += 1
            elif diff_days > 1:
                new_streak = 1
        else:
            new_streak = 1

        # Guest bukan member: poin, XP, dan streak tidak boleh ikut naik, kalau tidak
        # statistik member jadi angka satu "orang" berisi ribuan transaksi.
        if not is_guest:
            customer.points = new_points
            customer.xp = new_xp
            customer.level = new_level
            customer.lastVisitDate = now
            customer.pointsExpiryDate = expiry_date
            customer.streakCount = new_streak

        # Employee Quota Handling: the count comes from _resolve_line_items, not the client
        if customer.customerType == 'EMPLOYEE' and employee_quota_used > 0:
            customer.usedQuotaToday = min(customer.dailyQuota, (customer.usedQuotaToday or 0) + employee_quota_used)

        # Tax calculation (No parking fee)
        tax_pct = 11.0
        tax_setting = SystemSettings.query.filter_by(key='TAX_PERCENT').first() or SystemSettings.query.filter_by(key='TAX_PERCENTAGE').first()
        if tax_setting and tax_setting.value is not None:
            try:
                tax_pct = float(tax_setting.value)
            except ValueError:
                tax_pct = 11.0
        parking_fee = 0

        tax_mult = 1.0 + (tax_pct / 100.0)
        if tax_pct == 0:
            sub_total = total_amount
            tax_amount = 0
        else:
            sub_total = int(round(total_amount / tax_mult)) if total_amount > 0 else 0
            tax_amount = max(0, total_amount - sub_total)

        # Create Transaction
        transaction = Transaction(
            totalAmount=total_amount,
            subTotal=sub_total,
            taxAmount=tax_amount,
            parkingFee=0,
            discountAmount=discount_amount,
            pointsEarned=points_earned,
            paymentMethod=payment_method,
            customerId=customer.id,
            shiftId=shift_id,
            userId=cashier_id,
            status='COMPLETED',
            createdAt=now
        )
        db.session.add(transaction)
        db.session.flush()

        transaction.transactionCode = next_transaction_code(now)

        # Create Items & Deduct Ingredients
        tx_items = []
        for tx_data in tx_items_data:
            tx_item = TransactionItem(
                transactionId=transaction.id,
                menuId=tx_data['menuId'],
                quantity=tx_data['quantity'],
                price=tx_data['price'],
                discountAmount=tx_data['discountAmount'],
                hpp=tx_data['hpp']
            )
            db.session.add(tx_item)
            tx_items.append(tx_item)

        db.session.flush()

        # [REAL CAFE LOGIC]: Auto-deduct raw materials/inventory from stock based on recipe
        #
        # Pada input mundur ini bisa dimatikan: kalau riwayat lama dipindahkan,
        # stok fisik hari ini SUDAH mencerminkan penjualan itu, dan memotongnya
        # lagi membuat stok terjun minus. Untuk transaksi kemarin yang sekadar
        # lupa diinput, potongannya tetap harus jalan -- karena itu bawaannya
        # aktif dan hanya boleh dimatikan pada input mundur.
        potong_stok = True
        if is_backdated:
            potong_stok = data.get('deductStock', True) is not False
        if potong_stok:
            deduct_ingredients_for_order(transaction.id, tx_items, log_date=now)

        db.session.commit()

        # Gamification Async processing
        if not is_guest:
            process_gamification_async(customer.id, transaction.id)

        if is_backdated:
            alasan = (data.get('backdateReason') or '').strip() or 'tanpa alasan'
            log_activity('TRANSACTION_BACKDATED', cashier_id,
                         f"Input mundur ke {now:%Y-%m-%d %H:%M} - Rp {total_amount:,}".replace(',', '.')
                         + f" via {payment_method}; stok {'dipotong' if potong_stok else 'tidak dipotong'}"
                         + f"; alasan: {alasan}",
                         'Transaction', transaction.id)
        else:
            log_activity('TRANSACTION', cashier_id,
                         f"Total: Rp {total_amount:,} via {payment_method}".replace(',', '.'),
                         'Transaction', transaction.id)

        return jsonify({
            'message': 'Checkout successful',
            'customer': customer.to_dict(),
            'transaction': transaction.to_dict(include_items=True, include_customer=False),
            'luckyDrop': {'bonusPoints': bonus_points} if is_lucky_drop else None,
            'backdated': is_backdated,
            'stockDeducted': potong_stok,
            # Sesi kas kosong pada input mundur itu wajar (toko tutup, atau sesi
            # memang tidak dibuka saat itu) -- tapi kasir perlu tahu, karena
            # transaksinya tidak akan muncul di rekonsiliasi laci mana pun.
            'shiftId': shift_id
        }), 201
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        print(f"Error during checkout: {e}")
        return jsonify({'error': 'Failed to process checkout', 'details': str(e)}), 500


@checkout_bp.route('/sync', methods=['POST'])
def sync_checkout():
    data = request.get_json() or {}
    transactions_data = data.get('transactions', [])

    if not isinstance(transactions_data, list):
        return jsonify({'error': 'Invalid transactions data'}), 400

    try:
        tax_pct = 11.0
        tax_setting = SystemSettings.query.filter_by(key='TAX_PERCENT').first() or SystemSettings.query.filter_by(key='TAX_PERCENTAGE').first()
        if tax_setting and tax_setting.value is not None:
            try:
                tax_pct = float(tax_setting.value)
            except ValueError:
                tax_pct = 11.0
        parking_setting = SystemSettings.query.filter_by(key='PARKING_FEE').first()
        exp_setting = SystemSettings.query.filter_by(key='POINT_EXPIRATION_DAYS').first()

        cfg_parking = int(parking_setting.value) if parking_setting and parking_setting.value.isdigit() else 2000
        exp_days = int(exp_setting.value) if exp_setting and exp_setting.value.isdigit() else 90
        tax_mult = 1.0 + (tax_pct / 100.0)
        supervisor = is_supervisor()

        open_shift = _get_open_shift()
        shift_id = open_shift.id if open_shift else None
        cashier_id = _current_cashier_id()

        results = []
        rejected = []
        for tx in transactions_data:
            nickname = tx.get('nickname')
            customer_id = tx.get('customerId')
            items = tx.get('items', [])
            reward_id = tx.get('rewardId')
            payment_method = tx.get('paymentMethod', 'CASH')
            created_at_str = tx.get('createdAt')

            if not items:
                rejected.append({'nickname': nickname, 'reason': 'Order items cannot be empty'})
                continue

            customer, resolve_err = _resolve_customer(customer_id, nickname)
            if resolve_err:
                rejected.append({'nickname': nickname, 'reason': resolve_err[0]})
                continue
            nickname = customer.nickname
            is_guest = _is_guest(customer)
            customer.check_and_reset_quota()

            reward = None
            points_to_deduct = 0
            if reward_id:
                reward = Reward.query.get(int(reward_id))
                if not (reward and reward.active and customer and customer.points >= reward.pointsRequired):
                    reward = None
                else:
                    points_to_deduct = reward.pointsRequired

            # Same server-side pricing rules as the online checkout path
            tx_items_data, gross_total, employee_quota_used, err = _resolve_line_items(
                items, customer, supervisor
            )
            if err:
                rejected.append({'nickname': nickname, 'reason': err[0]})
                continue

            discount_amount, err = _resolve_order_discount(
                reward, tx.get('discountAmount', 0), gross_total, supervisor
            )
            if err:
                rejected.append({'nickname': nickname, 'reason': err[0]})
                continue

            total_amount = max(0, gross_total - discount_amount)
            points_earned = 0 if is_guest else math.floor(total_amount / 1000)

            new_points = max(0, customer.points + points_earned - points_to_deduct)
            new_xp = customer.xp + points_earned
            new_level = math.floor(new_xp / 100) + 1

            tx_date = datetime.fromisoformat(created_at_str.replace('Z', '+00:00')) if created_at_str else datetime.utcnow()
            expiry_date = tx_date + timedelta(days=exp_days)

            new_streak = customer.streakCount or 0
            if customer.lastVisitDate:
                last_visit = customer.lastVisitDate.date()
                curr_date = tx_date.date()
                diff = (curr_date - last_visit).days
                if diff == 1:
                    new_streak += 1
                elif diff > 1:
                    new_streak = 1
            else:
                new_streak = 1

            if not is_guest:
                customer.points = new_points
                customer.xp = new_xp
                customer.level = new_level
                customer.lastVisitDate = tx_date
                customer.pointsExpiryDate = expiry_date
                customer.streakCount = new_streak

            if customer.customerType == 'EMPLOYEE' and employee_quota_used > 0:
                customer.usedQuotaToday = min(customer.dailyQuota, (customer.usedQuotaToday or 0) + employee_quota_used)

            parking_fee = cfg_parking if total_amount > cfg_parking else 0
            amount_without_parking = total_amount - parking_fee
            if tax_pct == 0:
                sub_total = amount_without_parking
                tax_amount = 0
            else:
                sub_total = int(round(amount_without_parking / tax_mult))
                tax_amount = amount_without_parking - sub_total

            transaction = Transaction(
                totalAmount=total_amount,
                subTotal=sub_total,
                taxAmount=tax_amount,
                parkingFee=parking_fee,
                discountAmount=discount_amount,
                pointsEarned=points_earned,
                paymentMethod=payment_method,
                customerId=customer.id,
                shiftId=shift_id,
                userId=cashier_id,
                status='COMPLETED',
                createdAt=tx_date
            )
            db.session.add(transaction)
            db.session.flush()

            tx_items = []
            for tx_data in tx_items_data:
                t_item = TransactionItem(
                    transactionId=transaction.id,
                    menuId=tx_data['menuId'],
                    quantity=tx_data['quantity'],
                    price=tx_data['price'],
                    discountAmount=tx_data['discountAmount'],
                    hpp=tx_data['hpp']
                )
                db.session.add(t_item)
                tx_items.append(t_item)

            db.session.flush()
            deduct_ingredients_for_order(transaction.id, tx_items)
            results.append(transaction)

        db.session.commit()

        guest = Customer.query.filter_by(nickname=GUEST_NICKNAME).first()
        guest_id = guest.id if guest else None
        for res_tx in results:
            if res_tx.customerId != guest_id:
                process_gamification_async(res_tx.customerId, res_tx.id)

        return jsonify({
            'message': 'Sync successful',
            'syncedCount': len(results),
            'rejectedCount': len(rejected),
            'rejected': rejected
        }), 201
    except PeriodLockedError:
        raise      # ditangani errorhandler -> 423
    except Exception as e:
        db.session.rollback()
        print(f"Error during checkout sync: {e}")
        return jsonify({'error': 'Failed to process checkout sync'}), 500


@checkout_bp.route('/history/<int:id>/void', methods=['POST'])
def void_transaction(id):
    data = request.get_json() or {}
    void_reason = data.get('voidReason')

    # Attribution comes from the verified JWT, never from the request body
    if not is_supervisor():
        return jsonify({'error': 'Pembatalan transaksi memerlukan otorisasi Head Barista atau di atasnya'}), 403
    voided_by = get_current_user_id()

    import time
    for attempt in range(3):
        try:
            transaction = Transaction.query.get(id)
            if not transaction:
                return jsonify({'error': 'Transaction not found'}), 404
            if transaction.status == 'VOID':
                return jsonify({'error': 'Transaction already voided'}), 400

            # Membatalkan transaksi di periode yang sudah ditutup akan mengubah
            # omzet yang laporannya sudah dicetak dan mungkin sudah disetor.
            assert_period_open(transaction.createdAt)

            transaction.status = 'VOID'
            transaction.voidReason = void_reason
            transaction.voidedAt = datetime.utcnow()
            transaction.voidedBy = voided_by

            # Revert points & XP earned
            if transaction.pointsEarned > 0 and transaction.customerId:
                customer = Customer.query.get(transaction.customerId)
                if customer:
                    customer.points = max(0, customer.points - transaction.pointsEarned)
                    customer.xp = max(0, customer.xp - transaction.pointsEarned)

            # [REAL CAFE LOGIC]: Restore inventory materials
            restore_ingredients_for_void(transaction.id, transaction.items)

            db.session.commit()

            log_activity('VOID_TRANSACTION', voided_by,
                         void_reason, 'Transaction', transaction.id)

            return jsonify(transaction.to_dict(include_items=True, include_customer=True))
        except PeriodLockedError:
            raise      # ditangani errorhandler -> 423
        except Exception as e:
            db.session.rollback()
            if attempt < 2 and '1205' in str(e):
                time.sleep(0.3)
                continue
            print(f"Error voiding transaction: {e}")
            return jsonify({'error': 'Failed to void transaction'}), 500
