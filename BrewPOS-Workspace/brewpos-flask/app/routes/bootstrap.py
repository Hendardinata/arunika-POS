"""
Satu panggilan untuk semua yang dibutuhkan kerangka halaman.

Setiap halaman sebelumnya memanggil /api/settings, /api/shift/current, dan
/api/notifications secara terpisah. Di jaringan lokal itu tidak terasa; lewat
Tailscale, tiga perjalanan bolak-balik terjadi sebelum halaman bisa dipakai --
dan itu berulang di SETIAP pindah halaman.
"""
from flask import Blueprint, jsonify

bootstrap_bp = Blueprint('bootstrap', __name__, url_prefix='/api/bootstrap')


@bootstrap_bp.route('', methods=['GET'])
def get_bootstrap():
    hasil = {'settings': {}, 'currentShift': None,
             'notifications': {'items': [], 'count': 0, 'urgent': 0},
             'cashSessionEnabled': True}

    # Tiap bagian dibungkus sendiri: satu bagian gagal tidak boleh membuat
    # kerangka halaman kehilangan semuanya.
    try:
        from app.models.system_settings import SystemSettings
        hasil['settings'] = {s.key: s.value for s in SystemSettings.query.all()}
    except Exception as e:
        print(f"[Bootstrap] settings: {e}")

    try:
        from app.routes.shift import _get_open_shift, _sweep_stale_shifts, cash_session_enabled
        hasil['cashSessionEnabled'] = cash_session_enabled()
        if hasil['cashSessionEnabled']:
            _sweep_stale_shifts()
            shift = _get_open_shift()
            hasil['currentShift'] = shift.to_dict() if shift else None
    except Exception as e:
        print(f"[Bootstrap] shift: {e}")

    try:
        from app.routes.notifications import _kumpulkan
        catatan = _kumpulkan()
        hasil['notifications'] = {
            'items': catatan,
            'count': len(catatan),
            'urgent': sum(1 for c in catatan if c['level'] == 'danger'),
        }
    except Exception as e:
        print(f"[Bootstrap] notifications: {e}")

    return jsonify(hasil)
