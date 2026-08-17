from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from app.extensions import db
from app.models.expense import Expense
from app.models.shift import Shift, CashMovement
from app.models.attendance import ShiftHandover
from app.models.user import User
from app.models.transaction import Transaction
from app.middleware.auth import token_required, is_supervisor
from app.models.system_settings import get_setting_int
from app.services.system_logger import log_activity

shift_bp = Blueprint('shift', __name__, url_prefix='/api/shift')

# Sesi yang terlupa ditutup tidak boleh menggantung selamanya dan merusak angka kas.
STALE_SHIFT_HOURS = 20   # bawaan; ditimpa pengaturan SHIFT_MAX_HOURS


def cash_session_enabled():
    """
    Sesi kas bisa dimatikan lewat pengaturan.

    Gunanya kontrol kas: modal awal + transaksi tunai - pengeluaran tunai
    dibandingkan dengan uang yang benar-benar dihitung di laci. Kedai yang
    kasirnya pemilik sendiri sering tidak membutuhkannya, dan penanda "perlu
    ditutup" yang muncul terus jadi gangguan tanpa manfaat.

    Mematikannya tidak menghilangkan jejak siapa yang melayani: itu disimpan di
    Transaction.userId, terpisah dari sesi kas.
    """
    from app.models.system_settings import get_setting
    return get_setting('CASH_SESSION_ENABLED', '1') != '0'


def _sweep_stale_shifts():
    """Tandai sesi OPEN yang sudah kelewat lama. Dipanggil saat baca, tanpa scheduler."""
    if not cash_session_enabled():
        return
    batas = get_setting_int('SHIFT_MAX_HOURS', STALE_SHIFT_HOURS)
    cutoff = datetime.utcnow() - timedelta(hours=batas)
    stale = Shift.query.filter(Shift.status == 'OPEN', Shift.startTime < cutoff).all()
    if not stale:
        return
    for s in stale:
        s.status = 'NEEDS_REVIEW'
    db.session.commit()


def _get_open_shift():
    """
    Sesi kas milik toko, bukan milik satu kasir: siapa pun yang login ikut sesi ini.
    NEEDS_REVIEW tetap dihitung terbuka supaya masih bisa ditutup dan direkonsiliasi.
    """
    return Shift.query.filter(Shift.status.in_(['OPEN', 'NEEDS_REVIEW'])) \
                      .order_by(Shift.startTime.desc()).first()


def find_shift_at(waktu):
    """
    Sesi kas yang sedang berjalan pada suatu waktu, untuk transaksi yang diinput
    mundur.

    Tanpa ini transaksi bertanggal kemarin akan menempel ke sesi yang terbuka
    SEKARANG (lihat _get_open_shift), sehingga uang kemarin ikut dihitung sebagai
    isi laci hari ini dan memunculkan selisih kas palsu.

    Boleh mengembalikan None: sesi bisa berlubang (toko tutup, atau kasir lupa
    membuka sesi). Itu bukan galat -- transaksinya tetap tercatat, hanya tidak
    ikut rekonsiliasi laci mana pun.
    """
    return Shift.query.filter(
        Shift.startTime <= waktu,
        db.or_(Shift.endTime.is_(None), Shift.endTime >= waktu)
    ).order_by(Shift.startTime.desc()).first()


def _next_session_no():
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return Shift.query.filter(Shift.startTime >= today).count() + 1


@shift_bp.route('/open', methods=['POST'])
@token_required
def open_shift():
    data = request.get_json() or {}
    starting_cash = int(data.get('startingCash', 0))
    user_id = g.user.get('id')

    if not cash_session_enabled():
        return jsonify({'error': 'Sesi kas dimatikan di Pengaturan. '
                                 'Penjualan tetap bisa jalan tanpa sesi.'}), 409

    try:
        _sweep_stale_shifts()
        existing = _get_open_shift()
        if existing:
            return jsonify({
                'error': 'Masih ada sesi kas yang terbuka di toko ini',
                'shift': existing.to_dict()
            }), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        session_no = _next_session_no()
        shift = Shift(
            userId=user_id,
            openedBy=user_id,
            currentUserId=user_id,
            sessionNo=session_no,
            type=f"SESI {session_no}",
            status='OPEN',
            startingCash=starting_cash,
            startTime=datetime.utcnow()
        )
        db.session.add(shift)
        db.session.commit()

        return jsonify(shift.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error opening shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/current', methods=['GET'])
@token_required
def get_current_shift():
    try:
        _sweep_stale_shifts()
        shift = _get_open_shift()
        return jsonify({'currentShift': shift.to_dict() if shift else None})
    except Exception as e:
        print(f"Error fetching current shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/handover', methods=['POST'])
@token_required
def handover_shift():
    """Ganti penjaga di tengah sesi. Kas tidak dihitung ulang, hanya jejaknya dicatat."""
    data = request.get_json() or {}
    user_id = g.user.get('id')
    to_user_id = int(data.get('toUserId') or user_id)
    note = (data.get('note') or '').strip() or None

    try:
        shift = _get_open_shift()
        if not shift:
            return jsonify({'error': 'Tidak ada sesi kas yang terbuka'}), 404

        if shift.currentUserId == to_user_id:
            return jsonify({'error': 'Penjaga sesi sudah orang yang sama'}), 400

        if not User.query.get(to_user_id):
            return jsonify({'error': 'User tujuan tidak ditemukan'}), 404

        handover = ShiftHandover(
            shiftId=shift.id,
            fromUserId=shift.currentUserId,
            toUserId=to_user_id,
            note=note
        )

        # Hitung laci saat berganti penjaga. Opsional: pergantian sebentar
        # (ke belakang, salat) tidak perlu dihitung, dan memaksanya akan
        # membuat orang mengarang angka.
        selisih = None
        if data.get('countedCash') not in (None, ''):
            try:
                dihitung = int(data.get('countedCash'))
            except (TypeError, ValueError):
                return jsonify({'error': 'Hitungan kas harus berupa angka'}), 400
            if dihitung < 0:
                return jsonify({'error': 'Hitungan kas tidak boleh negatif'}), 400

            saldo_awal, sejak, _ = _titik_awal_segmen(shift)
            diharapkan, _ = hitung_kas_seharusnya(shift, saldo_awal, sejak)
            selisih = dihitung - diharapkan

            toleransi = get_setting_int('CASH_DIFF_TOLERANCE', 5000)
            if abs(selisih) > toleransi and not note:
                return jsonify({
                    'error': f'Selisih kas Rp {abs(selisih):,}'.replace(',', '.')
                             + f" ({'lebih' if selisih > 0 else 'kurang'}) pada giliran ini. "
                             + 'Wajib diisi keterangan sebelum serah terima.',
                    'requiresNote': True, 'difference': selisih,
                }), 400

            handover.countedCash = dihitung
            handover.expectedCash = diharapkan
            handover.difference = selisih

        shift.currentUserId = to_user_id
        db.session.add(handover)
        db.session.commit()

        if selisih:
            log_activity('CASH_DIFFERENCE', user_id,
                         f"Serah terima sesi #{shift.id}: selisih Rp {selisih:,}".replace(',', '.')
                         + f" pada giliran {handover.fromUser.username if handover.fromUser else '-'}"
                         + f" ({note or 'tanpa keterangan'})", 'Shift', shift.id)

        hasil = shift.to_dict()
        hasil['handover'] = handover.to_dict()
        return jsonify(hasil), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error handing over shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


def _titik_awal_segmen(shift):
    """
    Dari mana penghitungan laci dimulai. -> (saldo_awal, waktu_awal, penjaga)

    Kalau sudah pernah ada serah terima yang menghitung laci, penghitungan
    dimulai dari hitungan itu -- bukan dari modal awal sesi. Ini yang membuat
    selisih bisa dilokalisir: kalau giliran pertama kurang Rp 50.000 dan
    lacinya tidak dibetulkan, penjaga berikutnya tidak ikut disalahkan untuk
    kekurangan yang bukan miliknya.
    """
    terakhir = ShiftHandover.query.filter(
        ShiftHandover.shiftId == shift.id,
        ShiftHandover.countedCash.isnot(None)
    ).order_by(ShiftHandover.createdAt.desc()).first()

    if terakhir:
        return terakhir.countedCash, terakhir.createdAt, terakhir.toUserId
    return shift.startingCash, shift.startTime, shift.currentUserId


def hitung_kas_seharusnya(shift, saldo_awal=None, sejak=None):
    """
    Isi laci yang seharusnya. -> (expected, rincian)

    saldo awal + penjualan tunai - belanja dari laci - setoran keluar + tambahan masuk

    Dua suku terakhir yang sebelumnya tidak ada. Tanpa keduanya, setiap kali
    uang disetor ke brankas atau receh ditambah, selisihnya muncul sebagai
    "kas kurang/lebih" yang tidak bisa dijelaskan siapa pun.

    saldo_awal & sejak dipakai untuk menghitung satu giliran saja; tanpa
    keduanya, dihitung sejak sesi dibuka.
    """
    if saldo_awal is None:
        saldo_awal = shift.startingCash
    if sejak is None:
        sejak = shift.startTime

    tx = Transaction.query.filter(
        Transaction.shiftId == shift.id, Transaction.status == 'COMPLETED',
        Transaction.createdAt >= sejak).all()
    cash_income = sum(t.totalAmount for t in tx if t.paymentMethod == 'CASH')

    cash_expense = int(db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.shiftId == shift.id,
        Expense.paymentSource == 'CASH_DRAWER',
        Expense.date >= sejak
    ).scalar() or 0)

    gerakan = CashMovement.query.filter(
        CashMovement.shiftId == shift.id, CashMovement.createdAt >= sejak).all()
    drops = sum(m.amount for m in gerakan if m.type == 'DROP')
    paid_ins = sum(m.amount for m in gerakan if m.type == 'PAID_IN')

    expected = saldo_awal + cash_income - cash_expense - drops + paid_ins
    return expected, {
        'startingCash': saldo_awal,
        'cashSales': cash_income,
        'cashExpenses': cash_expense,
        'cashDrops': drops,
        'cashPaidIns': paid_ins,
        'expectedEndingCash': expected,
        'since': sejak.isoformat() if sejak else None,
    }


@shift_bp.route('/cash-movement', methods=['POST'])
@token_required
def add_cash_movement():
    """Catat uang keluar/masuk laci di luar penjualan dan belanja."""
    data = request.get_json() or {}
    jenis = (data.get('type') or '').upper()
    alasan = (data.get('reason') or '').strip()

    if jenis not in ('DROP', 'PAID_IN'):
        return jsonify({'error': 'Jenis harus DROP (keluar) atau PAID_IN (masuk)'}), 400
    try:
        jumlah = int(data.get('amount') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Jumlah harus berupa angka'}), 400
    if jumlah <= 0:
        return jsonify({'error': 'Jumlah harus lebih dari 0'}), 400
    # Alasan wajib: inilah satu-satunya jejak kenapa uang berpindah. Tanpa itu
    # catatannya tidak bisa dibedakan dari uang hilang.
    if len(alasan) < 3:
        return jsonify({'error': 'Alasan wajib diisi (mis. "setor ke brankas")'}), 400

    shift = _get_open_shift()
    if not shift:
        return jsonify({'error': 'Belum ada sesi kas terbuka'}), 409

    gerakan = CashMovement(shiftId=shift.id, type=jenis, amount=jumlah,
                           reason=alasan, userId=g.user.get('id'))
    db.session.add(gerakan)
    db.session.commit()

    log_activity('CASH_MOVEMENT', g.user.get('id'),
                 f"{'Keluar' if jenis == 'DROP' else 'Masuk'} laci Rp {jumlah:,}".replace(',', '.')
                 + f" - {alasan}", 'Shift', shift.id)
    return jsonify(gerakan.to_dict()), 201


@shift_bp.route('/cash-movement', methods=['GET'])
@token_required
def list_cash_movements():
    shift = _get_open_shift()
    if not shift:
        return jsonify({'items': [], 'net': 0})
    gerakan = CashMovement.query.filter_by(shiftId=shift.id) \
        .order_by(CashMovement.createdAt.desc()).all()
    return jsonify({
        'items': [m.to_dict() for m in gerakan],
        'net': sum(m.signed_amount() for m in gerakan),
    })


@shift_bp.route('/cash-movement/<int:id>', methods=['DELETE'])
@token_required
def delete_cash_movement(id):
    """Hapus catatan yang salah input. Hanya selama sesinya masih terbuka."""
    gerakan = CashMovement.query.get(id)
    if not gerakan:
        return jsonify({'error': 'Catatan tidak ditemukan'}), 404
    if not is_supervisor():
        return jsonify({'error': 'Menghapus catatan kas memerlukan Head Barista ke atas'}), 403

    shift = Shift.query.get(gerakan.shiftId)
    if shift and shift.status == 'CLOSED':
        return jsonify({'error': 'Sesi sudah ditutup, catatan kasnya tidak bisa diubah'}), 409

    db.session.delete(gerakan)
    db.session.commit()
    return jsonify({'message': 'Dihapus'})


@shift_bp.route('/close', methods=['POST'])
@token_required
def close_shift():
    data = request.get_json() or {}
    ending_cash = int(data.get('endingCash', 0))
    closing_note = (data.get('closingNote') or '').strip() or None
    user_id = g.user.get('id')

    try:
        shift = _get_open_shift()
        if not shift:
            return jsonify({'error': 'No open shift found'}), 404

        # Dihitung dari serah terima terakhir yang menghitung laci, bukan dari
        # modal awal sesi -- kalau tidak, penjaga terakhir menanggung selisih
        # yang sudah terjadi jauh sebelum gilirannya.
        saldo_awal, sejak, _ = _titik_awal_segmen(shift)
        expected_ending_cash, rincian = hitung_kas_seharusnya(shift, saldo_awal, sejak)
        selisih = ending_cash - expected_ending_cash

        # Ringkasan seluruh sesi tetap dilaporkan untuk pemilik: giliran boleh
        # dinilai sendiri-sendiri, tapi uang toko dihitung utuh.
        _, rincian_sesi = hitung_kas_seharusnya(shift)
        rincian['sesiPenuh'] = rincian_sesi

        # Selisih besar wajib dijelaskan. Kalau boleh ditutup tanpa keterangan,
        # angkanya cuma jadi hiasan: tidak ada yang menelusuri, dan bulan depan
        # tidak ada yang ingat kenapa kurang Rp 200.000.
        toleransi = get_setting_int('CASH_DIFF_TOLERANCE', 5000)
        if abs(selisih) > toleransi and not closing_note:
            return jsonify({
                'error': f'Selisih kas Rp {abs(selisih):,}'.replace(',', '.')
                         + f" ({'lebih' if selisih > 0 else 'kurang'}). "
                         + 'Wajib diisi keterangan sebelum sesi ditutup.',
                'requiresNote': True,
                'difference': selisih,
            }), 400

        shift.status = 'CLOSED'
        shift.endTime = datetime.utcnow()
        shift.endingCash = ending_cash
        shift.expectedEndingCash = expected_ending_cash
        shift.closedBy = user_id
        shift.closingNote = closing_note

        db.session.commit()

        if selisih:
            log_activity('CASH_DIFFERENCE', user_id,
                         f"Sesi #{shift.id} selisih Rp {selisih:,}".replace(',', '.')
                         + f" ({closing_note or 'tanpa keterangan'})", 'Shift', shift.id)

        hasil = shift.to_dict()
        hasil['breakdown'] = rincian
        hasil['difference'] = selisih
        return jsonify(hasil)
    except Exception as e:
        db.session.rollback()
        print(f"Error closing shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/reports', methods=['GET'])
def get_shift_reports():
    try:
        _sweep_stale_shifts()
        # to_dict(include_transactions=True) menyusuri transaksi tiap sesi.
        shifts = Shift.query.options(
            selectinload(Shift.transactions),
            selectinload(Shift.handovers),
        ).order_by(Shift.createdAt.desc()).limit(50).all()
        return jsonify([s.to_dict(include_transactions=True) for s in shifts])
    except Exception as e:
        print(f"Error fetching shift reports: {e}")
        return jsonify({'error': 'Internal server error'}), 500
