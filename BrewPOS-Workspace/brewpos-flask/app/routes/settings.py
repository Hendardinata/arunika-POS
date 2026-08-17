from datetime import date, datetime

from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.system_settings import SystemSettings
from app.models.transaction import Transaction
from app.services.system_logger import log_activity
from app.services.period_lock import LOCK_KEY, as_date, get_lock_date
from app.middleware.auth import get_current_user_id, is_admin, is_supervisor

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

# Setelan yang mengubah uang atau mengunci pembukuan. Sisanya (nama toko,
# format struk) tidak berbahaya dan tetap boleh disetel supervisor.
SETELAN_SENSITIF = {'TAX_PERCENT', 'TAX_PERCENTAGE', 'PARKING_FEE',
                    'POINT_EXPIRATION_DAYS', 'EMPLOYEE_DAILY_QUOTA', LOCK_KEY}

@settings_bp.route('', methods=['GET'])
def get_settings():
    try:
        settings = SystemSettings.query.all()
        return jsonify([s.to_dict() for s in settings])
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@settings_bp.route('', methods=['POST'])
def update_setting():
    data = request.get_json() or {}
    key = data.get('key')
    value = data.get('value')
    description = data.get('description')

    if not key or value is None:
        return jsonify({'error': 'Key and value are required'}), 400

    # Endpoint ini sempat tanpa gerbang peran sama sekali: kasir bisa mengubah
    # persentase pajak dan masa berlaku poin.
    if key in SETELAN_SENSITIF and not is_admin():
        return jsonify({'error': f'Mengubah {key} memerlukan otorisasi Admin'}), 403
    if key not in SETELAN_SENSITIF and not is_supervisor():
        return jsonify({'error': 'Mengubah pengaturan memerlukan Head Barista atau di atasnya'}), 403

    # Tanggal kunci hanya boleh maju lewat jalur ini. Memundurkannya berarti
    # membuka kembali periode yang sudah ditutup -- itu keputusan besar dan
    # punya endpointnya sendiri supaya tidak terjadi karena salah ketik.
    if key == LOCK_KEY:
        return jsonify({
            'error': 'Tutup buku diatur lewat /api/settings/period-lock, bukan di sini'
        }), 400

    try:
        setting = SystemSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
            if description is not None:
                setting.description = description
        else:
            setting = SystemSettings(key=key, value=str(value), description=description)
            db.session.add(setting)

        db.session.commit()

        user_id = get_current_user_id()
        user_id_int = int(user_id) if user_id else None
        log_activity('UPDATE_SETTINGS', user_id_int,
                     f"Updated setting {key} to {value}", 'SystemSettings', setting.id)

        return jsonify(setting.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500


def _set_lock_date(nilai):
    row = SystemSettings.query.filter_by(key=LOCK_KEY).first()
    teks = nilai.isoformat() if nilai else ''
    if row:
        row.value = teks
    else:
        db.session.add(SystemSettings(
            key=LOCK_KEY, value=teks,
            description='Tutup buku: transaksi pada/sebelum tanggal ini terkunci'))
    db.session.commit()


@settings_bp.route('/period-lock', methods=['GET'])
def get_period_lock():
    kunci = get_lock_date()
    belum_terkunci = Transaction.query.filter(Transaction.status == 'COMPLETED')
    if kunci:
        belum_terkunci = belum_terkunci.filter(
            Transaction.createdAt > datetime.combine(kunci, datetime.max.time()))
    return jsonify({
        'lockDate': kunci.isoformat() if kunci else None,
        'openTransactions': belum_terkunci.count(),
    })


@settings_bp.route('/period-lock', methods=['POST'])
def set_period_lock():
    """Tutup buku sampai suatu tanggal. Hanya maju."""
    if not is_admin():
        return jsonify({'error': 'Tutup buku memerlukan otorisasi Admin'}), 403

    tanggal = as_date((request.get_json() or {}).get('lockDate'))
    if not tanggal:
        return jsonify({'error': 'Tanggal tutup buku tidak terbaca'}), 400
    if tanggal > date.today():
        return jsonify({'error': 'Tidak bisa menutup buku untuk tanggal yang belum terjadi'}), 400

    sekarang = get_lock_date()
    if sekarang and tanggal <= sekarang:
        return jsonify({
            'error': f'Buku sudah tertutup sampai {sekarang.isoformat()}. '
                     'Memundurkan tanggal berarti membuka kembali periode -- pakai Buka Kembali.'
        }), 400

    _set_lock_date(tanggal)
    log_activity('PERIOD_CLOSE', int(get_current_user_id() or 0) or None,
                 f"Tutup buku sampai {tanggal.isoformat()}"
                 + (f" (sebelumnya {sekarang.isoformat()})" if sekarang else ""),
                 'SystemSettings', None)
    return jsonify({'lockDate': tanggal.isoformat()})


@settings_bp.route('/period-lock/reopen', methods=['POST'])
def reopen_period():
    """
    Buka kembali periode yang sudah ditutup.

    Sengaja endpoint tersendiri dan menuntut alasan: ini membuat angka yang
    laporannya sudah dicetak bisa berubah lagi, jadi harus ada jejaknya siapa
    yang memutuskan dan kenapa.
    """
    if not is_admin():
        return jsonify({'error': 'Membuka kembali periode memerlukan otorisasi Admin'}), 403

    data = request.get_json() or {}
    alasan = (data.get('reason') or '').strip()
    if len(alasan) < 5:
        return jsonify({'error': 'Alasan membuka kembali periode wajib diisi'}), 400

    sekarang = get_lock_date()
    if not sekarang:
        return jsonify({'error': 'Belum ada periode yang ditutup'}), 400

    baru = as_date(data.get('lockDate'))   # kosong = buka semuanya
    if baru and baru >= sekarang:
        return jsonify({'error': 'Tanggal baru harus lebih awal dari tanggal kunci sekarang'}), 400

    _set_lock_date(baru)
    log_activity('PERIOD_REOPEN', int(get_current_user_id() or 0) or None,
                 f"Buka kembali dari {sekarang.isoformat()} ke "
                 f"{baru.isoformat() if baru else 'terbuka semua'}; alasan: {alasan}",
                 'SystemSettings', None)
    return jsonify({'lockDate': baru.isoformat() if baru else None})
