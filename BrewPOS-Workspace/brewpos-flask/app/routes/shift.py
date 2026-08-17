from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from sqlalchemy import func
from app.extensions import db
from app.models.expense import Expense
from app.models.shift import Shift
from app.models.attendance import ShiftHandover
from app.models.user import User
from app.models.transaction import Transaction
from app.middleware.auth import token_required

shift_bp = Blueprint('shift', __name__, url_prefix='/api/shift')

# Sesi yang terlupa ditutup tidak boleh menggantung selamanya dan merusak angka kas.
STALE_SHIFT_HOURS = 18


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
    cutoff = datetime.utcnow() - timedelta(hours=STALE_SHIFT_HOURS)
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
        shift.currentUserId = to_user_id
        db.session.add(handover)
        db.session.commit()

        return jsonify(shift.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error handing over shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


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

        # Calculate expected cash from CASH transactions
        cash_income = 0
        transactions = Transaction.query.filter_by(shiftId=shift.id, status='COMPLETED').all()
        for t in transactions:
            if t.paymentMethod == 'CASH':
                cash_income += t.totalAmount

        # Uang yang diambil dari laci untuk belanja ikut dihitung, kalau tidak
        # setiap pembelian tunai muncul sebagai "kas kurang" yang palsu.
        cash_expense = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.shiftId == shift.id,
            Expense.paymentSource == 'CASH_DRAWER'
        ).scalar() or 0

        expected_ending_cash = shift.startingCash + cash_income - int(cash_expense)

        shift.status = 'CLOSED'
        shift.endTime = datetime.utcnow()
        shift.endingCash = ending_cash
        shift.expectedEndingCash = expected_ending_cash
        shift.closedBy = user_id
        shift.closingNote = closing_note

        db.session.commit()
        return jsonify(shift.to_dict())
    except Exception as e:
        db.session.rollback()
        print(f"Error closing shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/reports', methods=['GET'])
def get_shift_reports():
    try:
        _sweep_stale_shifts()
        shifts = Shift.query.order_by(Shift.createdAt.desc()).limit(50).all()
        return jsonify([s.to_dict(include_transactions=True) for s in shifts])
    except Exception as e:
        print(f"Error fetching shift reports: {e}")
        return jsonify({'error': 'Internal server error'}), 500
