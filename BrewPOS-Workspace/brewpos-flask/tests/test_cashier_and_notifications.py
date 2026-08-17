"""
Penjualan per kasir + pemberitahuan operasional.

Yang dijaga: atribusi kasir diambil dari siapa yang MEMPROSES transaksi (bukan
siapa yang membuka sesi kas -- satu laci dipakai bergantian), dan pemberitahuan
hilang sendiri begitu masalahnya beres.
"""
from datetime import datetime, timedelta

from app.extensions import db
from app.models.customer import Customer
from app.models.inventory import InventoryItem
from app.models.shift import Shift
from app.models.system_settings import SystemSettings
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User


def _tx(user, nominal, menu, status='COMPLETED', metode='CASH', hpp=6000, qty=1):
    c = Customer.query.first()
    if not c:
        c = Customer(nickname='Guest', points=0, xp=0, level=1, streakCount=0)
        db.session.add(c)
        db.session.flush()
    t = Transaction(subTotal=nominal, totalAmount=nominal, taxAmount=0, status=status,
                    customerId=c.id, userId=user.id if user else None, paymentMethod=metode)
    db.session.add(t)
    db.session.flush()
    db.session.add(TransactionItem(transactionId=t.id, menuId=menu.id, quantity=qty,
                                   price=nominal, hpp=hpp))
    db.session.commit()
    return t


# --- Penjualan per kasir ----------------------------------------------------

def test_penjualan_dikelompokkan_per_kasir(client, app, menu, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    kasir = User.query.filter_by(role='CASHIER').first()
    _tx(admin, 50000, menu)
    _tx(admin, 30000, menu)
    _tx(kasir, 20000, menu)

    isi = client.get('/api/analytics/by-cashier?days=all', headers=admin_headers).get_json()
    per_nama = {r['username']: r for r in isi['items']}

    assert per_nama['superadmin']['orders'] == 2
    assert per_nama['superadmin']['revenue'] == 80000
    assert per_nama['kasir']['revenue'] == 20000
    assert isi['totalRevenue'] == 100000
    # Urut dari omzet terbesar
    assert isi['items'][0]['username'] == 'superadmin'


def test_void_dipisahkan_dari_omzet(client, app, menu, admin_headers):
    """Void tidak boleh menaikkan omzet kasir, tapi harus tetap terlihat."""
    admin = User.query.filter_by(role='SUPERADMIN').first()
    _tx(admin, 50000, menu)
    _tx(admin, 90000, menu, status='VOID')

    r = client.get('/api/analytics/by-cashier?days=all',
                   headers=admin_headers).get_json()['items'][0]
    assert r['revenue'] == 50000
    assert r['orders'] == 1
    assert r['voidCount'] == 1 and r['voidAmount'] == 90000


def test_laba_kotor_dan_rata_rata_per_struk(client, app, menu, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    _tx(admin, 50000, menu, hpp=20000)
    _tx(admin, 30000, menu, hpp=10000)

    r = client.get('/api/analytics/by-cashier?days=all',
                   headers=admin_headers).get_json()['items'][0]
    assert r['hpp'] == 30000
    assert r['grossProfit'] == 50000
    assert r['avgPerOrder'] == 40000


def test_metode_bayar_dirinci(client, app, menu, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    _tx(admin, 50000, menu, metode='CASH')
    _tx(admin, 30000, menu, metode='QRIS')

    r = client.get('/api/analytics/by-cashier?days=all',
                   headers=admin_headers).get_json()['items'][0]
    assert r['byPayment'] == {'CASH': 50000, 'QRIS': 30000}


def test_transaksi_tanpa_kasir_tetap_muncul(client, app, menu, admin_headers):
    """Baris lama bisa tidak punya userId; jangan sampai omzetnya hilang diam-diam."""
    _tx(None, 40000, menu)
    isi = client.get('/api/analytics/by-cashier?days=all', headers=admin_headers).get_json()
    assert isi['totalRevenue'] == 40000
    assert isi['items'][0]['username'] == 'Tidak tercatat'


def test_rincian_satu_kasir_bisa_ditelusuri(client, app, menu, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    _tx(admin, 50000, menu)
    kasir = User.query.filter_by(role='CASHIER').first()
    _tx(kasir, 20000, menu)

    isi = client.get(f'/api/analytics/cashier/{admin.id}?days=all',
                     headers=admin_headers).get_json()
    assert isi['count'] == 1
    assert isi['items'][0]['totalAmount'] == 50000


# --- Pemberitahuan ----------------------------------------------------------

def test_bahan_habis_muncul_sebagai_peringatan(client, app, bean, admin_headers):
    bean.stock = 0
    db.session.commit()

    isi = client.get('/api/notifications', headers=admin_headers).get_json()
    ids = [n['id'] for n in isi['items']]
    assert 'stok-habis' in ids
    assert isi['urgent'] >= 1


def test_peringatan_hilang_setelah_masalahnya_beres(client, app, bean, admin_headers):
    """
    Pemberitahuan diturunkan dari keadaan sekarang, bukan riwayat kejadian --
    jadi tidak ada baris usang yang perlu dibersihkan.
    """
    bean.stock = 0
    db.session.commit()
    assert 'stok-habis' in [n['id'] for n in
                            client.get('/api/notifications', headers=admin_headers).get_json()['items']]

    bean.stock = 5000
    db.session.commit()
    assert 'stok-habis' not in [n['id'] for n in
                                client.get('/api/notifications', headers=admin_headers).get_json()['items']]


def test_bahan_tanpa_harga_diperingatkan(client, app, admin_headers):
    """Harga 0 membuat HPP nol dan margin terlihat 100% -- salah arah yang mahal."""
    db.session.add(InventoryItem(name='Gula Aren', unit='ml', stock=1000, minStock=100))
    db.session.commit()

    ids = [n['id'] for n in client.get('/api/notifications',
                                       headers=admin_headers).get_json()['items']]
    assert 'bahan-tanpa-harga' in ids


def test_sesi_kelewat_lama_diperingatkan(client, app, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    db.session.add(Shift(type='SESI 1', sessionNo=1,
                         startTime=datetime.utcnow() - timedelta(hours=40),
                         status='OPEN', startingCash=200000,
                         userId=admin.id, openedBy=admin.id))
    db.session.commit()

    judul = ' '.join(n['title'] for n in client.get('/api/notifications',
                                                    headers=admin_headers).get_json()['items'])
    assert 'jam terbuka' in judul


def test_selisih_kas_besar_diperingatkan(client, app, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    db.session.add(Shift(type='SESI 1', sessionNo=1, startTime=datetime.utcnow() - timedelta(hours=8),
                         endTime=datetime.utcnow(), status='CLOSED', startingCash=200000,
                         expectedEndingCash=900000, endingCash=700000,
                         closingNote='belum ketemu', userId=admin.id, openedBy=admin.id))
    db.session.commit()

    isi = client.get('/api/notifications', headers=admin_headers).get_json()
    assert any('selisih' in n['id'] for n in isi['items'])
    assert isi['urgent'] >= 1


def test_sesi_kas_dimatikan_tidak_memunculkan_peringatan_sesi(client, app, admin_headers):
    db.session.add(SystemSettings(key='CASH_SESSION_ENABLED', value='0'))
    admin = User.query.filter_by(role='SUPERADMIN').first()
    db.session.add(Shift(type='SESI 1', sessionNo=1,
                         startTime=datetime.utcnow() - timedelta(hours=40),
                         status='OPEN', startingCash=200000,
                         userId=admin.id, openedBy=admin.id))
    db.session.commit()

    judul = ' '.join(n['title'] for n in client.get('/api/notifications',
                                                    headers=admin_headers).get_json()['items'])
    assert 'jam terbuka' not in judul


def test_yang_mendesak_diurutkan_lebih_dulu(client, app, bean, admin_headers):
    """Kalau yang genting tenggelam di bawah, orang berhenti membuka loncengnya."""
    bean.stock = 0
    db.session.commit()

    item = client.get('/api/notifications', headers=admin_headers).get_json()['items']
    tingkat = [n['level'] for n in item]
    assert tingkat == sorted(tingkat, key=lambda l: {'danger': 0, 'warning': 1, 'info': 2}[l])
