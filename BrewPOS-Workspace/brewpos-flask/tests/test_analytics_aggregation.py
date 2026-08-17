"""
Agregasi analitik dipindah dari Python ke SQL demi kecepatan.

Yang diuji di sini bukan kecepatannya, tapi bahwa angkanya TETAP SAMA. Optimasi
yang mengubah angka laporan jauh lebih berbahaya daripada laporan yang lambat --
lambat kelihatan, salah tidak.

Setiap angka dibandingkan dengan hitungan Python lugas atas data yang sama.
"""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.expense import Expense, ExpenseCategory
from app.models.menu import Menu
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User


@pytest.fixture
def data(app, menu):
    """Data yang sengaja beragam: beda hari, metode, status, diskon, kasir."""
    admin = User.query.filter_by(role='SUPERADMIN').first()
    kasir = User.query.filter_by(role='CASHIER').first()
    c = Customer(nickname='Uji', points=0, xp=0, level=1, streakCount=0)
    kat = ExpenseCategory(name='Operasional')
    db.session.add_all([c, kat])
    db.session.flush()

    kedua = Menu(name='Menu Kedua', price=15000, hpp=4000,
                 categoryId=menu.categoryId)
    db.session.add(kedua)
    db.session.flush()

    skenario = [
        # (hari_lalu, total, diskon_order, metode, status, user, menu, qty, diskon_item, hpp)
        (0, 50000, 0, 'CASH', 'COMPLETED', admin, menu, 2, 0, 6000),
        (0, 30000, 5000, 'QRIS', 'COMPLETED', admin, kedua, 1, 1000, 4000),
        (1, 45000, 0, 'CASH', 'COMPLETED', kasir, menu, 1, 0, 6000),
        (1, 25000, 0, 'DEBIT', 'COMPLETED', kasir, kedua, 3, 500, 4000),
        (2, 90000, 0, 'CASH', 'VOID', admin, menu, 2, 0, 6000),
        (3, 60000, 10000, 'CASH', 'COMPLETED', admin, menu, 1, 0, 6000),
    ]
    for hari, total, disc, metode, status, user, m, qty, disc_item, hpp in skenario:
        waktu = datetime.utcnow() - timedelta(days=hari, hours=2)
        t = Transaction(subTotal=total, totalAmount=total, taxAmount=int(total * 0.11),
                        parkingFee=0, discountAmount=disc, status=status,
                        customerId=c.id, userId=user.id, paymentMethod=metode,
                        createdAt=waktu)
        db.session.add(t)
        db.session.flush()
        db.session.add(TransactionItem(transactionId=t.id, menuId=m.id, quantity=qty,
                                       price=m.price, discountAmount=disc_item, hpp=hpp))

    db.session.add(Expense(amount=75000, date=datetime.utcnow() - timedelta(days=1),
                           categoryId=kat.id, userId=admin.id))
    db.session.commit()


def _python_totals(status='COMPLETED'):
    """Hitungan lugas di Python, sebagai pembanding."""
    tx = Transaction.query.filter_by(status=status).all()
    return {
        'revenue': sum(t.totalAmount for t in tx),
        'orders': len(tx),
        'hpp': sum((i.hpp or 0) * i.quantity for t in tx for i in t.items),
        'tax': sum(t.taxAmount for t in tx),
        'gross': sum(t.subTotal + (t.discountAmount or 0) for t in tx),
        'discounts': sum((t.discountAmount or 0)
                         + sum((i.discountAmount or 0) * i.quantity for i in t.items)
                         for t in tx),
    }


def test_dashboard_angkanya_sama_dengan_hitungan_python(client, app, data, admin_headers):
    p = _python_totals()
    isi = client.get('/api/analytics?days=all', headers=admin_headers).get_json()

    assert isi['totalRevenue'] == p['revenue']
    assert isi['totalOrders'] == p['orders']
    assert isi['totalHpp'] == p['hpp']
    assert isi['totalExpenses'] == 75000
    assert isi['netProfit'] == p['revenue'] - p['hpp'] - 75000


def test_void_tidak_ikut_omzet_dashboard(client, app, data, admin_headers):
    isi = client.get('/api/analytics?days=all', headers=admin_headers).get_json()
    semua = sum(t.totalAmount for t in Transaction.query.all())
    assert isi['totalRevenue'] < semua      # yang VOID tidak ikut


def test_deret_harian_menjumlah_penuh(client, app, data, admin_headers):
    """Total grafik harus sama dengan total omzet; kalau tidak, ada hari yang hilang."""
    isi = client.get('/api/analytics?days=all', headers=admin_headers).get_json()
    assert sum(d['revenue'] for d in isi['chartData']) == isi['totalRevenue']


def test_deret_harian_memisahkan_hari_dengan_benar(client, app, data, admin_headers):
    isi = client.get('/api/analytics?days=all', headers=admin_headers).get_json()
    berisi = [d for d in isi['chartData'] if d['revenue'] > 0]
    # Skenario menaruh transaksi sah di 3 hari berbeda (hari VOID tidak dihitung)
    assert len(berisi) == 3


def test_menu_terlaris_cocok_dengan_hitungan_python(client, app, data, admin_headers):
    tx = Transaction.query.filter_by(status='COMPLETED').all()
    harap = {}
    for t in tx:
        for i in t.items:
            nama = i.menu.name
            harap[nama] = harap.get(nama, 0) + i.quantity

    isi = client.get('/api/analytics?days=all', headers=admin_headers).get_json()
    dapat = {m['name']: m['count'] for m in isi['popularMenus']}
    assert dapat == harap


def test_laporan_lengkap_ringkasannya_cocok(client, app, data, admin_headers):
    p = _python_totals()
    isi = client.get('/api/analytics/comprehensive-reports?days=all',
                     headers=admin_headers).get_json()
    s = isi['salesSummary']

    assert s['totalNet'] == p['revenue']
    assert s['totalOrders'] == p['orders']
    assert s['totalTax'] == p['tax']
    assert s['totalGross'] == p['gross']
    assert s['totalDiscounts'] == p['discounts']
    assert s['totalVoid'] == 1
    assert s['totalVoidAmount'] == 90000


def test_ringkasan_tetap_utuh_walau_daftar_barisnya_dibatasi(client, app, data, admin_headers):
    """
    Daftar baris dibatasi supaya laporan setahun tidak perlu menserialisasi
    puluhan ribu baris. Angka ringkasannya harus tetap dihitung atas SELURUH
    rentang -- kalau ikut terpotong, laporan berbohong tanpa kelihatan.
    """
    p = _python_totals()
    isi = client.get('/api/analytics/comprehensive-reports?days=all&limit=50',
                     headers=admin_headers).get_json()

    assert isi['salesSummary']['totalNet'] == p['revenue']
    assert isi['salesSummary']['totalOrders'] == p['orders']
    assert isi['transactionsTotal'] == p['orders']
    assert isi['transactionsShown'] <= 50


def test_klien_diberi_tahu_kalau_daftarnya_dipotong(client, app, data, admin_headers):
    isi = client.get('/api/analytics/comprehensive-reports?days=all&limit=50',
                     headers=admin_headers).get_json()
    # 5 transaksi sah, batas 50 -> tidak dipotong
    assert isi['transactionsTruncated'] is False
    assert 'transactionsTotal' in isi


def test_metode_bayar_dirinci_benar(client, app, data, admin_headers):
    harap = {}
    for t in Transaction.query.filter_by(status='COMPLETED').all():
        harap[t.paymentMethod] = harap.get(t.paymentMethod, 0) + t.totalAmount

    isi = client.get('/api/analytics/comprehensive-reports?days=all',
                     headers=admin_headers).get_json()
    assert isi['salesSummary']['byPaymentMethod'] == harap


def test_per_kasir_cocok_dengan_hitungan_python(client, app, data, admin_headers):
    harap = {}
    for t in Transaction.query.filter_by(status='COMPLETED').all():
        n = t.cashier.username
        d = harap.setdefault(n, {'orders': 0, 'revenue': 0, 'items': 0, 'hpp': 0})
        d['orders'] += 1
        d['revenue'] += t.totalAmount
        d['items'] += sum(i.quantity for i in t.items)
        d['hpp'] += sum((i.hpp or 0) * i.quantity for i in t.items)

    isi = client.get('/api/analytics/by-cashier?days=all', headers=admin_headers).get_json()
    for r in isi['items']:
        h = harap[r['username']]
        assert (r['orders'], r['revenue'], r['items'], r['hpp']) == \
               (h['orders'], h['revenue'], h['items'], h['hpp'])


def test_filter_rentang_tanggal_masih_menyempitkan(client, app, data, admin_headers):
    """Agregasi SQL tetap harus menghormati filter tanggal."""
    semua = client.get('/api/analytics?days=all', headers=admin_headers).get_json()
    hari_ini = client.get('/api/analytics?days=1', headers=admin_headers).get_json()
    assert hari_ini['totalRevenue'] < semua['totalRevenue']
    assert hari_ini['totalOrders'] < semua['totalOrders']
