"""
Omzet harian dari masa sebelum go-live.

Toko sudah berjualan sebelum aplikasi ini ada, tapi catatan lamanya cuma sampai
"tanggal sekian omzetnya sekian". Yang dijaga di sini: angka itu masuk ke
laporan pendapatan, TAPI tidak merembes ke tempat yang tidak punya datanya --
stok, poin member, HPP, dan profitabilitas per menu.
"""
from datetime import date, datetime, timedelta

from app.extensions import db
from app.models.historical_sales import HistoricalSales
from app.models.inventory import InventoryItem, InventoryLog
from app.models.transaction import Transaction


def _kirim(client, headers, **kw):
    muatan = {'date': '2026-07-01', 'totalAmount': 1500000}
    muatan.update(kw)
    return client.post('/api/historical-sales', headers=headers, json=muatan)


def test_menyimpan_omzet_harian(client, admin_headers):
    res = _kirim(client, admin_headers, transactionCount=42, notes='Dari buku kas')
    assert res.status_code == 201, res.get_json()
    isi = res.get_json()
    assert isi['date'] == '2026-07-01'
    assert isi['totalAmount'] == 1500000
    assert isi['transactionCount'] == 42


def test_tanggal_yang_sama_diperbaiki_bukan_digandakan(client, admin_headers):
    """Salah ketik lalu ketik ulang tidak boleh menggandakan omzet diam-diam."""
    _kirim(client, admin_headers, totalAmount=1000000)
    res = _kirim(client, admin_headers, totalAmount=1750000)
    assert res.status_code == 200, res.get_json()

    rows = HistoricalSales.query.filter_by(date=date(2026, 7, 1)).all()
    assert len(rows) == 1
    assert rows[0].totalAmount == 1750000


def test_tanggal_masa_depan_ditolak(client, admin_headers):
    besok = (date.today() + timedelta(days=1)).isoformat()
    assert _kirim(client, admin_headers, date=besok).status_code == 400


def test_tanggal_ngawur_ditolak(client, admin_headers):
    assert _kirim(client, admin_headers, date='kemarin').status_code == 400
    assert _kirim(client, admin_headers, date='').status_code == 400


def test_angka_tidak_masuk_akal_ditolak(client, admin_headers):
    assert _kirim(client, admin_headers, totalAmount=-1).status_code == 400
    assert _kirim(client, admin_headers, totalAmount='banyak').status_code == 400
    assert _kirim(client, admin_headers, transactionCount=-3).status_code == 400


def test_menolak_tanggal_yang_sudah_ada_penjualan_kasir(client, app, admin_headers, menu):
    """
    Kalau hari itu sudah tercatat lewat kasir, menambah omzet lama di tanggal
    yang sama berarti menghitungnya dua kali -- dan tidak ada yang menyadarinya
    sampai laporan bulanan meleset.
    """
    from app.models.customer import Customer
    c = Customer(nickname='Uji', points=0, xp=0, level=1, streakCount=0)
    db.session.add(c)
    db.session.flush()
    db.session.add(Transaction(subTotal=50000, totalAmount=50000, taxAmount=0,
                               status='COMPLETED', customerId=c.id,
                               createdAt=datetime(2026, 7, 1, 10, 0)))
    db.session.commit()

    res = _kirim(client, admin_headers, date='2026-07-01')
    assert res.status_code == 409
    assert 'dua kali' in res.get_json()['error']
    assert HistoricalSales.query.count() == 0


def test_tidak_menyentuh_stok_maupun_mutasinya(client, app, admin_headers, bean):
    """Stok fisik hari ini sudah mencerminkan penjualan lama itu."""
    stok_awal = bean.stock
    log_awal = InventoryLog.query.count()

    _kirim(client, admin_headers)

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).stock == stok_awal
    assert InventoryLog.query.count() == log_awal


def test_tidak_membuat_transaksi_bayangan(client, app, admin_headers):
    """Kalau tersimpan sebagai Transaction, laporan per menu akan berbohong."""
    _kirim(client, admin_headers)
    assert Transaction.query.count() == 0


def test_daftar_menjumlahkan_totalnya(client, admin_headers):
    _kirim(client, admin_headers, date='2026-07-01', totalAmount=1000000)
    _kirim(client, admin_headers, date='2026-07-02', totalAmount=1200000)

    isi = client.get('/api/historical-sales', headers=admin_headers).get_json()
    assert isi['days'] == 2
    assert isi['totalAmount'] == 2200000


def test_bisa_dihapus(client, admin_headers):
    id_baris = _kirim(client, admin_headers).get_json()['id']
    assert client.delete(f'/api/historical-sales/{id_baris}', headers=admin_headers).status_code == 200
    assert HistoricalSales.query.count() == 0
    assert client.delete(f'/api/historical-sales/{id_baris}', headers=admin_headers).status_code == 404


def test_masuk_laporan_sebagai_angka_terpisah(client, app, admin_headers):
    """
    Ikut ke pendapatan, tapi terpisah -- totalRevenue harus tetap murni dari
    kasir supaya HPP dan margin di bawahnya tidak ikut bergeser oleh angka
    yang tidak punya rincian menu.
    """
    _kirim(client, admin_headers, date='2026-07-01', totalAmount=1500000)

    isi = client.get('/api/analytics?days=all', headers=admin_headers).get_json()
    assert isi['historicalRevenue'] == 1500000
    assert isi['totalRevenue'] == 0            # belum ada penjualan lewat kasir
    assert isi['totalRevenueWithHistorical'] == 1500000
    # HPP tidak boleh mengarang modal untuk omzet tanpa rincian menu
    assert isi['totalHpp'] == 0
    assert isi['popularMenus'] == []
