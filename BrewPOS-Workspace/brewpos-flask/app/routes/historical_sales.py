"""
Omzet harian sebelum go-live.

Toko sudah berjualan sebelum aplikasi ini ada. Catatan lamanya cuma sampai
tingkat "tanggal sekian omzetnya sekian", jadi yang bisa dipindahkan hanya
angka itu -- bukan rincian menunya.
"""
from datetime import date, datetime

from flask import Blueprint, request, jsonify

from app.extensions import db
from app.middleware.auth import get_current_user_id
from app.models.historical_sales import HistoricalSales
from app.models.transaction import Transaction
from app.services.system_logger import log_activity

historical_bp = Blueprint('historical_sales', __name__, url_prefix='/api/historical-sales')


def _baca_tanggal(nilai):
    if not nilai:
        return None
    try:
        return datetime.fromisoformat(str(nilai).replace('Z', '+00:00')).date()
    except ValueError:
        try:
            return datetime.strptime(str(nilai)[:10], '%Y-%m-%d').date()
        except ValueError:
            return None


@historical_bp.route('', methods=['GET'])
def list_historical():
    rows = HistoricalSales.query.order_by(HistoricalSales.date.desc()).all()
    return jsonify({
        'items': [r.to_dict() for r in rows],
        'totalAmount': sum(r.totalAmount for r in rows),
        'days': len(rows),
    })


@historical_bp.route('', methods=['POST'])
def upsert_historical():
    """
    Satu baris per tanggal. Mengirim tanggal yang sama dua kali berarti
    memperbaiki angkanya, bukan menambah baris kedua -- kalau tidak, salah ketik
    lalu ketik ulang akan menggandakan omzet tanpa terlihat.
    """
    data = request.get_json() or {}
    tanggal = _baca_tanggal(data.get('date'))
    if not tanggal:
        return jsonify({'error': 'Tanggal tidak terbaca (pakai format YYYY-MM-DD)'}), 400
    if tanggal > date.today():
        return jsonify({'error': 'Tanggal belum terjadi'}), 400

    try:
        total = int(data.get('totalAmount') or 0)
    except (TypeError, ValueError):
        return jsonify({'error': 'Omzet harus berupa angka'}), 400
    if total < 0:
        return jsonify({'error': 'Omzet tidak boleh negatif'}), 400

    jumlah_struk = data.get('transactionCount')
    if jumlah_struk not in (None, ''):
        try:
            jumlah_struk = int(jumlah_struk)
        except (TypeError, ValueError):
            return jsonify({'error': 'Jumlah struk harus berupa angka'}), 400
        if jumlah_struk < 0:
            return jsonify({'error': 'Jumlah struk tidak boleh negatif'}), 400
    else:
        jumlah_struk = None

    # Tanggal yang sudah ada penjualan sungguhannya hampir pasti salah ketik:
    # hari itu sudah tercatat lewat kasir, menambah omzet lama akan menghitungnya
    # dua kali dan tidak ada yang menyadarinya sampai laporan bulanan meleset.
    awal = datetime.combine(tanggal, datetime.min.time())
    akhir = datetime.combine(tanggal, datetime.max.time())
    sudah_ada = Transaction.query.filter(
        Transaction.status == 'COMPLETED',
        Transaction.createdAt >= awal, Transaction.createdAt <= akhir).count()
    if sudah_ada:
        return jsonify({
            'error': f'Tanggal {tanggal.isoformat()} sudah punya {sudah_ada} transaksi dari kasir. '
                     'Menambahkan omzet lama di tanggal yang sama akan terhitung dua kali.'
        }), 409

    row = HistoricalSales.query.filter_by(date=tanggal).first()
    baru = row is None
    if baru:
        row = HistoricalSales(date=tanggal)
        db.session.add(row)

    row.totalAmount = total
    row.transactionCount = jumlah_struk
    row.notes = (data.get('notes') or '').strip() or None
    db.session.commit()

    user_id = get_current_user_id()
    log_activity('HISTORICAL_SALES', int(user_id) if user_id else None,
                 f"{'Tambah' if baru else 'Perbarui'} omzet lama {tanggal.isoformat()}: "
                 f"Rp {total:,}".replace(',', '.'), 'HistoricalSales', row.id)

    return jsonify(row.to_dict()), 201 if baru else 200


@historical_bp.route('/<int:id>', methods=['DELETE'])
def delete_historical(id):
    row = HistoricalSales.query.get(id)
    if not row:
        return jsonify({'error': 'Data tidak ditemukan'}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({'message': 'Dihapus'})
