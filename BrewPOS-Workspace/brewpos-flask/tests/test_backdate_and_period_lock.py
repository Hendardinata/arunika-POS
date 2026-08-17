"""
Transaksi bertanggal mundur + tutup buku.

Yang dijaga di sini bukan sekadar "tanggalnya tersimpan", tapi bahwa input
mundur TIDAK merusak hal-hal yang menempel pada "hari ini": isi laci kas, kuota
karyawan, nomor struk, dan stok.
"""
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.inventory import InventoryItem, InventoryLog
from app.models.shift import Shift
from app.models.system_settings import SystemSettings
from app.models.transaction import Transaction
from app.models.user import User

KEMARIN = datetime.utcnow() - timedelta(days=1)


def _pesan(client, headers, waktu=None, **kw):
    muatan = {'nickname': 'Guest', 'items': [{'menuId': 1, 'quantity': 1}], 'paymentMethod': 'CASH'}
    if waktu:
        muatan['createdAt'] = waktu.isoformat()
    muatan.update(kw)
    return client.post('/api/checkout', headers=headers, json=muatan)


@pytest.fixture
def sesi_terbuka(app):
    """Sesi kas yang sedang berjalan hari ini. Belum ada fixture semacam ini."""
    admin = User.query.filter_by(role='SUPERADMIN').first()
    s = Shift(type='SESI 1', sessionNo=1, startTime=datetime.utcnow() - timedelta(hours=1),
              status='OPEN', startingCash=200000, userId=admin.id, openedBy=admin.id)
    db.session.add(s)
    db.session.commit()
    return s


def _kunci_sampai(tanggal):
    db.session.add(SystemSettings(key='PERIOD_LOCK_DATE', value=tanggal.isoformat()))
    db.session.commit()


# --- Gerbang peran ----------------------------------------------------------

def test_kasir_biasa_tidak_boleh_input_mundur(client, menu, cashier_headers):
    res = _pesan(client, cashier_headers, KEMARIN)
    assert res.status_code == 403
    assert 'Head Barista' in res.get_json()['error']


def test_supervisor_boleh_input_mundur(client, menu, headbar_headers):
    res = _pesan(client, headbar_headers, KEMARIN)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['backdated'] is True

    tx = Transaction.query.first()
    assert tx.createdAt.date() == KEMARIN.date()


def test_transaksi_biasa_tidak_terpengaruh(client, menu, cashier_headers):
    """Kasir biasa harus tetap bisa jualan seperti sebelumnya."""
    res = _pesan(client, cashier_headers)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['backdated'] is False
    assert Transaction.query.first().createdAt.date() == datetime.utcnow().date()


# --- Validasi tanggal -------------------------------------------------------

def test_tanggal_masa_depan_ditolak(client, menu, admin_headers):
    res = _pesan(client, admin_headers, datetime.utcnow() + timedelta(days=1))
    assert res.status_code == 400


def test_tanggal_ngawur_ditolak(client, menu, admin_headers):
    res = _pesan(client, admin_headers, createdAt='besok pagi')
    assert res.status_code == 400


def test_tanggal_yang_sudah_ada_omzet_lamanya_ditolak(client, menu, admin_headers):
    """Kalau tidak, omzet hari itu terhitung dua kali di laporan."""
    client.post('/api/historical-sales', headers=admin_headers,
                json={'date': KEMARIN.date().isoformat(), 'totalAmount': 500000})
    res = _pesan(client, admin_headers, KEMARIN)
    assert res.status_code == 409
    assert 'omzet lama' in res.get_json()['error']


# --- Sesi kas ---------------------------------------------------------------

def test_transaksi_mundur_tidak_masuk_laci_hari_ini(client, app, menu, admin_headers, sesi_terbuka):
    """
    Ini inti perbaikannya. Sebelumnya transaksi mundur menempel ke sesi yang
    terbuka sekarang, sehingga uang kemarin ikut dihitung sebagai isi laci hari
    ini dan memunculkan selisih kas palsu.
    """
    res = _pesan(client, admin_headers, KEMARIN)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['shiftId'] != sesi_terbuka.id

    db.session.expire_all()
    assert Transaction.query.first().shiftId != sesi_terbuka.id


def test_transaksi_biasa_tetap_masuk_sesi_yang_terbuka(client, app, menu, admin_headers, sesi_terbuka):
    res = _pesan(client, admin_headers)
    assert res.get_json()['shiftId'] == sesi_terbuka.id


def test_sesi_yang_sudah_ditutup_ditandai_perlu_dicek(client, app, menu, admin_headers):
    """
    Lacinya sudah dihitung dan ditutup. Menulis ulang angkanya diam-diam justru
    menyembunyikan ketidakcocokan; yang benar adalah menandainya.
    """
    admin = User.query.filter_by(role='SUPERADMIN').first()
    s = Shift(type='SESI 1', sessionNo=1,
              startTime=KEMARIN - timedelta(hours=2), endTime=KEMARIN + timedelta(hours=2),
              status='CLOSED', startingCash=200000, expectedEndingCash=500000,
              endingCash=500000, userId=admin.id, openedBy=admin.id)
    db.session.add(s)
    db.session.commit()
    kas_sebelum = s.expectedEndingCash

    res = _pesan(client, admin_headers, KEMARIN)
    assert res.status_code == 201, res.get_json()

    db.session.expire_all()
    s = Shift.query.get(s.id)
    assert s.status == 'NEEDS_REVIEW'
    assert 'kas perlu dicek ulang' in (s.closingNote or '')
    # Angka kas yang tersimpan TIDAK ditulis ulang diam-diam
    assert s.expectedEndingCash == kas_sebelum


# --- Nomor struk ------------------------------------------------------------

def test_nomor_struk_tidak_kembar_saat_disisipkan_ke_hari_lampau(client, menu, admin_headers):
    """
    Penomoran sempat memakai count(), jadi menyisip ke hari lampau menghasilkan
    nomor yang sudah terpakai -- dan tidak ada unique constraint yang menangkap.
    """
    for _ in range(3):
        assert _pesan(client, admin_headers, KEMARIN).status_code == 201

    kode = [t.transactionCode for t in Transaction.query.all()]
    assert len(kode) == 3
    assert len(set(kode)) == 3, f'nomor struk kembar: {kode}'
    assert all(k.startswith('TR' + KEMARIN.strftime('%Y%m%d')) for k in kode)


# --- Stok -------------------------------------------------------------------

def test_input_mundur_memotong_stok_secara_bawaan(client, app, menu, bean, admin_headers):
    stok_awal = bean.stock
    assert _pesan(client, admin_headers, KEMARIN).status_code == 201

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).stock < stok_awal
    # Mutasinya bertanggal sama dengan transaksinya, bukan hari input
    log = InventoryLog.query.filter_by(itemId=bean.id, type='OUT').first()
    assert log.createdAt.date() == KEMARIN.date()


def test_potong_stok_bisa_dimatikan_untuk_memindahkan_riwayat(client, app, menu, bean, admin_headers):
    """Stok fisik hari ini sudah mencerminkan penjualan lama itu."""
    stok_awal = bean.stock
    res = _pesan(client, admin_headers, KEMARIN, deductStock=False)
    assert res.status_code == 201
    assert res.get_json()['stockDeducted'] is False

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).stock == stok_awal
    assert InventoryLog.query.filter_by(itemId=bean.id, type='OUT').count() == 0


def test_transaksi_biasa_tidak_bisa_melewati_potong_stok(client, app, menu, bean, cashier_headers):
    """deductStock hanya berlaku pada input mundur; kalau tidak, jadi celah."""
    stok_awal = bean.stock
    assert _pesan(client, cashier_headers, deductStock=False).status_code == 201

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).stock < stok_awal


# --- Kuota karyawan & undian poin -------------------------------------------

def test_kuota_karyawan_tidak_terpakai_oleh_input_mundur(client, app, menu, employee, admin_headers):
    """Kuota adalah jatah hari ini; input mundur tidak boleh memakannya."""
    terpakai_awal = employee.usedQuotaToday
    res = client.post('/api/checkout', headers=admin_headers, json={
        'customerId': employee.id, 'items': [{'menuId': menu.id, 'quantity': 1}],
        'paymentMethod': 'CASH', 'createdAt': KEMARIN.isoformat()})
    assert res.status_code == 201, res.get_json()

    db.session.expire_all()
    assert Customer.query.get(employee.id).usedQuotaToday == terpakai_awal


def test_input_mundur_tidak_pernah_dapat_undian_poin(client, app, menu, admin_headers):
    """Hadiah acak pada entri ulang tidak bisa diaudit dan bisa diulang-ulang."""
    c = Customer(nickname='Member Uji', points=0, xp=0, level=1, streakCount=0)
    db.session.add(c)
    db.session.commit()

    for _ in range(25):   # 20% peluang; 25x hampir pasti kena kalau aktif
        res = client.post('/api/checkout', headers=admin_headers, json={
            'customerId': c.id, 'items': [{'menuId': menu.id, 'quantity': 1}],
            'paymentMethod': 'CASH', 'createdAt': KEMARIN.isoformat()})
        assert res.status_code == 201, res.get_json()
        assert res.get_json()['luckyDrop'] is None


# --- Tutup buku -------------------------------------------------------------

def test_transaksi_di_periode_terkunci_ditolak(client, app, menu, admin_headers):
    _kunci_sampai(date.today() - timedelta(days=1))
    res = _pesan(client, admin_headers, KEMARIN)
    assert res.status_code == 423
    assert 'sudah ditutup' in res.get_json()['error']


def test_transaksi_hari_ini_tetap_jalan_walau_kemarin_terkunci(client, app, menu, cashier_headers):
    _kunci_sampai(date.today() - timedelta(days=1))
    assert _pesan(client, cashier_headers).status_code == 201


def test_void_di_periode_terkunci_ditolak(client, app, menu, admin_headers):
    tx_id = _pesan(client, admin_headers, KEMARIN).get_json()['transaction']['id']
    _kunci_sampai(date.today() - timedelta(days=1))

    res = client.post(f'/api/checkout/history/{tx_id}/void', headers=admin_headers,
                      json={'voidReason': 'salah input'})
    assert res.status_code == 423
    db.session.expire_all()
    assert Transaction.query.get(tx_id).status == 'COMPLETED'


def test_pengeluaran_di_periode_terkunci_ditolak(client, app, admin_headers):
    from app.models.expense import ExpenseCategory
    db.session.add(ExpenseCategory(name='Operasional'))
    db.session.commit()
    kat = ExpenseCategory.query.first()

    _kunci_sampai(date.today() - timedelta(days=1))
    res = client.post('/api/expenses', headers=admin_headers, json={
        'amount': 50000, 'categoryId': kat.id, 'date': KEMARIN.isoformat(), 'notes': 'uji'})
    assert res.status_code == 423


def test_pembelian_bahan_di_periode_terkunci_ditolak(client, app, bean, admin_headers):
    _kunci_sampai(date.today() - timedelta(days=1))
    res = client.post('/api/inventory/purchase', headers=admin_headers, json={
        'itemId': bean.id, 'quantity': 100, 'totalCost': 20000,
        'date': KEMARIN.date().isoformat()})
    assert res.status_code == 423


# --- Pengaturan tutup buku --------------------------------------------------

def test_hanya_admin_yang_boleh_tutup_buku(client, headbar_headers, admin_headers):
    tgl = (date.today() - timedelta(days=2)).isoformat()
    assert client.post('/api/settings/period-lock', headers=headbar_headers,
                       json={'lockDate': tgl}).status_code == 403
    assert client.post('/api/settings/period-lock', headers=admin_headers,
                       json={'lockDate': tgl}).status_code == 200


def test_tutup_buku_hanya_maju(client, admin_headers):
    client.post('/api/settings/period-lock', headers=admin_headers,
                json={'lockDate': (date.today() - timedelta(days=2)).isoformat()})
    res = client.post('/api/settings/period-lock', headers=admin_headers,
                      json={'lockDate': (date.today() - timedelta(days=5)).isoformat()})
    assert res.status_code == 400
    assert 'Buka Kembali' in res.get_json()['error']


def test_membuka_kembali_wajib_beralasan(client, admin_headers):
    client.post('/api/settings/period-lock', headers=admin_headers,
                json={'lockDate': (date.today() - timedelta(days=2)).isoformat()})

    assert client.post('/api/settings/period-lock/reopen', headers=admin_headers,
                       json={}).status_code == 400
    res = client.post('/api/settings/period-lock/reopen', headers=admin_headers,
                      json={'reason': 'salah tutup, nota belum masuk semua'})
    assert res.status_code == 200
    assert res.get_json()['lockDate'] is None


def test_pajak_tidak_bisa_diubah_kasir(client, cashier_headers, admin_headers):
    """Endpoint pengaturan sempat tanpa gerbang peran sama sekali."""
    assert client.post('/api/settings', headers=cashier_headers,
                       json={'key': 'TAX_PERCENT', 'value': '0'}).status_code == 403
    assert client.post('/api/settings', headers=admin_headers,
                       json={'key': 'TAX_PERCENT', 'value': '11'}).status_code == 200
