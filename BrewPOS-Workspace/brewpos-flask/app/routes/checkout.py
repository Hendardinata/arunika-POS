import random
import math
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.customer import Customer, GUEST_NICKNAME
from app.models.transaction import Transaction, TransactionItem
from app.models.menu import Menu
from app.models.reward import Reward
from app.models.system_settings import SystemSettings
from app.models.shift import Shift
from app.services.system_logger import log_activity
from app.services.gamification_service import process_gamification_async
from app.services.inventory_service import deduct_ingredients_for_order, restore_ingredients_for_void
from app.middleware.auth import get_current_user_id, is_supervisor

checkout_bp = Blueprint('checkout', __name__, url_prefix='/api/checkout')


def _current_cashier_id():
    user_id = get_current_user_id()
    return int(user_id) if user_id else None


def _get_open_shift():
    """Sesi kas milik toko; dipakai bersama semua kasir yang sedang login."""
    return Shift.query.filter(Shift.status.in_(['OPEN', 'NEEDS_REVIEW'])) \
                      .order_by(Shift.startTime.desc()).first()


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
        transactions = Transaction.query.order_by(Transaction.createdAt.desc()).limit(50).all()
        return jsonify([t.to_dict(include_items=True, include_customer=True) for t in transactions])
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
        customer.check_and_reset_quota()

        supervisor = is_supervisor()

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
        if random.random() < 0.20 and not is_guest:
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
        exp_setting = SystemSettings.query.filter_by(key='POINT_EXPIRATION_DAYS').first()
        exp_days = int(exp_setting.value) if exp_setting and exp_setting.value.isdigit() else 90
        now = datetime.utcnow()
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

        # Single Unified Transaction Prefix 'TR' + yyyyMMdd + 6-digit daily sequence (Total: 16 characters, e.g. TR20260814000001)
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
        today_end = datetime(now.year, now.month, now.day, 23, 59, 59)
        daily_count = Transaction.query.filter(
            Transaction.createdAt >= today_start,
            Transaction.createdAt <= today_end
        ).count()

        date_str = now.strftime('%Y%m%d')
        transaction.transactionCode = f"TR{date_str}{daily_count:06d}"

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
        deduct_ingredients_for_order(transaction.id, tx_items)

        db.session.commit()

        # Gamification Async processing
        if not is_guest:
            process_gamification_async(customer.id, transaction.id)

        log_activity('TRANSACTION', cashier_id,
                     f"Total: Rp {total_amount:,} via {payment_method}".replace(',', '.'),
                     'Transaction', transaction.id)

        return jsonify({
            'message': 'Checkout successful',
            'customer': customer.to_dict(),
            'transaction': transaction.to_dict(include_items=True, include_customer=False),
            'luckyDrop': {'bonusPoints': bonus_points} if is_lucky_drop else None
        }), 201
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
        except Exception as e:
            db.session.rollback()
            if attempt < 2 and '1205' in str(e):
                time.sleep(0.3)
                continue
            print(f"Error voiding transaction: {e}")
            return jsonify({'error': 'Failed to void transaction'}), 500
