"""
Pemberitahuan operasional.

Sengaja TIDAK punya tabel sendiri. Semuanya diturunkan dari keadaan data saat
ini, jadi tidak ada baris usang yang harus dibersihkan dan tidak mungkin ada
peringatan yang bertahan setelah masalahnya beres. Yang ditampilkan selalu
keadaan sekarang, bukan riwayat kejadian.

Isinya hanya hal yang bisa ditindaklanjuti hari ini. Peringatan yang tidak bisa
diapa-apakan akan diabaikan orang, dan sekali orang terbiasa mengabaikannya,
peringatan yang penting ikut terlewat.
"""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify

from app.extensions import db
from app.models.inventory import DailyOpname, InventoryItem
from app.models.shift import Shift
from app.models.system_settings import get_setting_int
from app.models.transaction import Transaction

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')

# Urutan tampil; yang bisa merugikan uang lebih dulu.
BOBOT = {'danger': 0, 'warning': 1, 'info': 2}


def _kumpulkan():
    catatan = []

    # --- Stok ---------------------------------------------------------------
    habis, menipis, tanpa_harga = [], [], []
    for i in InventoryItem.query.filter(InventoryItem.isActive == True).all():  # noqa: E712
        stok = i.stock or 0
        if stok <= 0:
            habis.append(i.name)
        elif stok <= (i.minStock or 0):
            menipis.append(i.name)
        if (i.costPerUnit or 0) <= 0:
            tanpa_harga.append(i.name)

    if habis:
        catatan.append({
            'id': 'stok-habis', 'level': 'danger', 'icon': 'box-open',
            'title': f'{len(habis)} bahan habis',
            'body': ', '.join(habis[:5]) + ('...' if len(habis) > 5 else ''),
            'link': '/inventory',
        })
    if menipis:
        catatan.append({
            'id': 'stok-menipis', 'level': 'warning', 'icon': 'triangle-exclamation',
            'title': f'{len(menipis)} bahan menipis',
            'body': ', '.join(menipis[:5]) + ('...' if len(menipis) > 5 else ''),
            'link': '/inventory',
        })
    if tanpa_harga:
        # Bahan berharga 0 membuat HPP nol dan margin terlihat 100% -- salah
        # arah yang mahal, karena keputusan harga jual diambil dari situ.
        catatan.append({
            'id': 'bahan-tanpa-harga', 'level': 'warning', 'icon': 'tag',
            'title': f'{len(tanpa_harga)} bahan belum ada harga beli',
            'body': 'Selama harganya kosong, modal menu terhitung 0 dan margin '
                    'terlihat 100%. ' + ', '.join(tanpa_harga[:5]),
            'link': '/inventory',
        })

    # --- Sesi kas -----------------------------------------------------------
    from app.routes.shift import cash_session_enabled
    if cash_session_enabled():
        sesi = Shift.query.filter(Shift.status.in_(['OPEN', 'NEEDS_REVIEW'])) \
                          .order_by(Shift.startTime.desc()).first()
        if sesi:
            jam = (datetime.utcnow() - sesi.startTime).total_seconds() / 3600
            batas = get_setting_int('SHIFT_MAX_HOURS', 20)
            if sesi.status == 'NEEDS_REVIEW' or jam > batas:
                catatan.append({
                    'id': f'sesi-lama-{sesi.id}', 'level': 'warning', 'icon': 'clock',
                    'title': f'{sesi.label()} sudah {int(jam)} jam terbuka',
                    'body': 'Tutup dan cocokkan kasnya supaya selisih tidak menumpuk '
                            'ke hari berikutnya.',
                    'link': None,
                })
        else:
            hari_ini = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            jualan = Transaction.query.filter(
                Transaction.createdAt >= hari_ini,
                Transaction.status == 'COMPLETED').count()
            if jualan:
                catatan.append({
                    'id': 'sesi-belum-dibuka', 'level': 'info', 'icon': 'cash-register',
                    'title': f'{jualan} transaksi hari ini tanpa sesi kas',
                    'body': 'Transaksinya tetap tercatat, tapi tidak ikut rekonsiliasi laci.',
                    'link': None,
                })

    # --- Selisih kas terakhir ----------------------------------------------
    tutup_terakhir = Shift.query.filter(Shift.status == 'CLOSED') \
                                .order_by(Shift.endTime.desc()).first()
    if tutup_terakhir and tutup_terakhir.expectedEndingCash is not None:
        selisih = (tutup_terakhir.endingCash or 0) - tutup_terakhir.expectedEndingCash
        toleransi = get_setting_int('CASH_DIFF_TOLERANCE', 5000)
        if abs(selisih) > toleransi:
            catatan.append({
                'id': f'selisih-kas-{tutup_terakhir.id}', 'level': 'danger', 'icon': 'scale-unbalanced',
                'title': f"Sesi terakhir selisih Rp {abs(selisih):,}".replace(',', '.')
                         + (' lebih' if selisih > 0 else ' kurang'),
                'body': tutup_terakhir.closingNote or 'Tanpa keterangan.',
                'link': '/reports',
            })

    # --- Opname -------------------------------------------------------------
    opname_terakhir = DailyOpname.query.order_by(DailyOpname.date.desc()).first()
    if not opname_terakhir:
        catatan.append({
            'id': 'opname-belum-pernah', 'level': 'info', 'icon': 'clipboard-check',
            'title': 'Belum pernah opname stok',
            'body': 'Opname menetapkan stok awal yang benar; tanpa itu angka stok '
                    'hanya hasil hitungan resep.',
            'link': '/inventory',
        })
    elif (datetime.utcnow() - opname_terakhir.date).days >= 7:
        catatan.append({
            'id': 'opname-lama', 'level': 'info', 'icon': 'clipboard-check',
            'title': f'Opname terakhir {(datetime.utcnow() - opname_terakhir.date).days} hari lalu',
            'body': 'Stok sistem makin jauh dari stok fisik kalau tidak dicocokkan.',
            'link': '/inventory',
        })

    catatan.sort(key=lambda c: BOBOT.get(c['level'], 3))
    return catatan


@notifications_bp.route('', methods=['GET'])
def list_notifications():
    try:
        catatan = _kumpulkan()
        return jsonify({
            'items': catatan,
            'count': len(catatan),
            # Titik merah di lonceng hanya untuk yang benar-benar mendesak.
            'urgent': sum(1 for c in catatan if c['level'] == 'danger'),
        })
    except Exception as e:
        # Pemberitahuan tidak boleh menjatuhkan halaman mana pun.
        print(f"[Notifications] {e}")
        return jsonify({'items': [], 'count': 0, 'urgent': 0})
