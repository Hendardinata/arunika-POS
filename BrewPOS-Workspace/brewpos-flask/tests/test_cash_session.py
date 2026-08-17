"""
Sesi kas untuk pemakaian nyata: kafe buka 08.00-24.00.

Yang dijaga di sini adalah aritmetika lacinya. Rekonsiliasi kas hanya berguna
kalau angkanya benar; sekali meleset, orang berhenti mempercayainya dan
kontrolnya mati walaupun fiturnya masih ada.
"""
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.expense import Expense, ExpenseCategory
from app.models.shift import CashMovement, Shift
from app.models.system_settings import SystemSettings
from app.models.transaction import Transaction
from app.models.user import User

MODAL_AWAL = 300000


@pytest.fixture
def sesi(client, admin_headers):
    res = client.post('/api/shift/open', headers=admin_headers,
                      json={'startingCash': MODAL_AWAL})
    assert res.status_code == 201, res.get_json()
    return Shift.query.first()


def _jual_tunai(sesi, nominal, metode='CASH'):
    c = Customer.query.first() or Customer(nickname='Guest', points=0, xp=0, level=1, streakCount=0)
    if not c.id:
        db.session.add(c)
        db.session.flush()
    db.session.add(Transaction(subTotal=nominal, totalAmount=nominal, taxAmount=0,
                               status='COMPLETED', customerId=c.id, shiftId=sesi.id,
                               paymentMethod=metode))
    db.session.commit()


def _belanja_dari_laci(sesi, nominal):
    kat = ExpenseCategory.query.first()
    if not kat:
        kat = ExpenseCategory(name='Operasional')
        db.session.add(kat)
        db.session.flush()
    admin = User.query.filter_by(role='SUPERADMIN').first()
    db.session.add(Expense(amount=nominal, date=datetime.utcnow(), categoryId=kat.id,
                           userId=admin.id, paymentSource='CASH_DRAWER', shiftId=sesi.id))
    db.session.commit()


# --- Uang keluar-masuk laci -------------------------------------------------

def test_setoran_ke_brankas_tercatat(client, sesi, admin_headers):
    res = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 500000, 'reason': 'Setor ke brankas, laci penuh'})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['signedAmount'] == -500000


def test_tambah_receh_tercatat(client, sesi, admin_headers):
    res = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'PAID_IN', 'amount': 100000, 'reason': 'Tambah receh dari brankas'})
    assert res.status_code == 201
    assert res.get_json()['signedAmount'] == 100000


def test_alasan_wajib_diisi(client, sesi, admin_headers):
    """Tanpa alasan, catatannya tidak bisa dibedakan dari uang hilang."""
    res = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 500000, 'reason': ''})
    assert res.status_code == 400
    assert 'Alasan' in res.get_json()['error']


def test_jumlah_tidak_masuk_akal_ditolak(client, sesi, admin_headers):
    for jumlah in (0, -5000):
        res = client.post('/api/shift/cash-movement', headers=admin_headers, json={
            'type': 'DROP', 'amount': jumlah, 'reason': 'setor'})
        assert res.status_code == 400


def test_jenis_ngawur_ditolak(client, sesi, admin_headers):
    res = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'AMBIL', 'amount': 10000, 'reason': 'entah'})
    assert res.status_code == 400


def test_tanpa_sesi_terbuka_ditolak(client, admin_headers):
    res = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 10000, 'reason': 'setor'})
    assert res.status_code == 409


# --- Aritmetika laci --------------------------------------------------------

def test_kas_seharusnya_memperhitungkan_semua_arus(client, app, sesi, admin_headers):
    """
    Skenario satu hari di kafe:
      modal 300.000 + tunai 1.200.000 - belanja 150.000
      - setor brankas 800.000 + tambah receh 200.000 = 750.000
    """
    _jual_tunai(sesi, 1200000)
    _jual_tunai(sesi, 500000, metode='QRIS')      # non-tunai tidak boleh ikut
    _belanja_dari_laci(sesi, 150000)
    client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 800000, 'reason': 'Setor brankas sore'})
    client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'PAID_IN', 'amount': 200000, 'reason': 'Tambah receh'})

    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': 750000})
    assert res.status_code == 200, res.get_json()
    isi = res.get_json()

    assert isi['breakdown'] == {
        'startingCash': 300000, 'cashSales': 1200000, 'cashExpenses': 150000,
        'cashDrops': 800000, 'cashPaidIns': 200000, 'expectedEndingCash': 750000,
    }
    assert isi['difference'] == 0


def test_setoran_tanpa_dicatat_dulunya_jadi_selisih_palsu(client, app, sesi, admin_headers):
    """
    Inti perbaikannya: uang yang disetor ke brankas dulu tidak terwakili, jadi
    laci selalu terlihat "kurang" sebesar setorannya.
    """
    _jual_tunai(sesi, 1000000)
    client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 900000, 'reason': 'Setor brankas'})

    # Uang fisik tersisa = 300.000 + 1.000.000 - 900.000
    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': 400000})
    assert res.get_json()['difference'] == 0


def test_transaksi_non_tunai_tidak_masuk_hitungan_laci(client, app, sesi, admin_headers):
    _jual_tunai(sesi, 250000, metode='QRIS')
    _jual_tunai(sesi, 100000, metode='DEBIT')
    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': MODAL_AWAL})
    assert res.get_json()['difference'] == 0


def test_transaksi_void_tidak_ikut_dihitung(client, app, sesi, admin_headers):
    _jual_tunai(sesi, 100000)
    tx = Transaction.query.first()
    tx.status = 'VOID'
    db.session.commit()

    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': MODAL_AWAL})
    assert res.get_json()['difference'] == 0


# --- Selisih kas ------------------------------------------------------------

def test_selisih_besar_wajib_dijelaskan(client, app, sesi, admin_headers):
    """
    Kalau boleh ditutup tanpa keterangan, angkanya cuma hiasan -- bulan depan
    tidak ada yang ingat kenapa kurang.
    """
    _jual_tunai(sesi, 1000000)
    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': 1100000})
    assert res.status_code == 400
    assert res.get_json()['requiresNote'] is True
    assert res.get_json()['difference'] == -200000

    db.session.expire_all()
    assert Shift.query.first().status != 'CLOSED'


def test_selisih_besar_bisa_ditutup_dengan_keterangan(client, app, sesi, admin_headers):
    _jual_tunai(sesi, 1000000)
    res = client.post('/api/shift/close', headers=admin_headers, json={
        'endingCash': 1100000, 'closingNote': 'Kembalian kelebihan ke pelanggan sore'})
    assert res.status_code == 200
    assert res.get_json()['difference'] == -200000


def test_selisih_kecil_lolos_tanpa_keterangan(client, app, sesi, admin_headers):
    """Selisih receh itu wajar; memaksa keterangan tiap hari bikin orang asal isi."""
    _jual_tunai(sesi, 1000000)
    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': 1298000})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['difference'] == -2000


def test_batas_toleransi_bisa_disetel(client, app, sesi, admin_headers):
    db.session.add(SystemSettings(key='CASH_DIFF_TOLERANCE', value='500'))
    db.session.commit()

    _jual_tunai(sesi, 1000000)
    res = client.post('/api/shift/close', headers=admin_headers, json={'endingCash': 1298000})
    assert res.status_code == 400


# --- Batas sesi basi --------------------------------------------------------

def test_sesi_16_jam_tidak_ditandai_bermasalah(client, app, admin_headers):
    """Kafe buka 08.00-24.00. Sesi 16 jam itu normal, bukan terlupa ditutup."""
    admin = User.query.filter_by(role='SUPERADMIN').first()
    s = Shift(type='SESI 1', sessionNo=1, startTime=datetime.utcnow() - timedelta(hours=16),
              status='OPEN', startingCash=MODAL_AWAL, userId=admin.id, openedBy=admin.id)
    db.session.add(s)
    db.session.commit()

    client.get('/api/shift/current', headers=admin_headers)
    db.session.expire_all()
    assert Shift.query.get(s.id).status == 'OPEN'


def test_batas_jam_sesi_bisa_disetel(client, app, admin_headers):
    """Jam buka bisa diperpanjang; batasnya ikut, bukan dipatok mati di kode."""
    db.session.add(SystemSettings(key='SHIFT_MAX_HOURS', value='30'))
    admin = User.query.filter_by(role='SUPERADMIN').first()
    s = Shift(type='SESI 1', sessionNo=1, startTime=datetime.utcnow() - timedelta(hours=25),
              status='OPEN', startingCash=MODAL_AWAL, userId=admin.id, openedBy=admin.id)
    db.session.add(s)
    db.session.commit()

    client.get('/api/shift/current', headers=admin_headers)
    db.session.expire_all()
    assert Shift.query.get(s.id).status == 'OPEN'


def test_sesi_yang_benar_benar_terlupa_tetap_ditandai(client, app, admin_headers):
    admin = User.query.filter_by(role='SUPERADMIN').first()
    s = Shift(type='SESI 1', sessionNo=1, startTime=datetime.utcnow() - timedelta(hours=40),
              status='OPEN', startingCash=MODAL_AWAL, userId=admin.id, openedBy=admin.id)
    db.session.add(s)
    db.session.commit()

    client.get('/api/shift/current', headers=admin_headers)
    db.session.expire_all()
    assert Shift.query.get(s.id).status == 'NEEDS_REVIEW'


# --- Koreksi & penutupan ----------------------------------------------------

def test_catatan_kas_salah_input_bisa_dihapus_supervisor(client, sesi, admin_headers, cashier_headers):
    id_gerakan = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 500000, 'reason': 'salah ketik'}).get_json()['id']

    assert client.delete(f'/api/shift/cash-movement/{id_gerakan}',
                         headers=cashier_headers).status_code == 403
    assert client.delete(f'/api/shift/cash-movement/{id_gerakan}',
                         headers=admin_headers).status_code == 200


def test_catatan_kas_terkunci_setelah_sesi_ditutup(client, app, sesi, admin_headers):
    id_gerakan = client.post('/api/shift/cash-movement', headers=admin_headers, json={
        'type': 'DROP', 'amount': 100000, 'reason': 'Setor brankas'}).get_json()['id']
    client.post('/api/shift/close', headers=admin_headers, json={'endingCash': 200000})

    res = client.delete(f'/api/shift/cash-movement/{id_gerakan}', headers=admin_headers)
    assert res.status_code == 409


def test_daftar_gerakan_kas_menjumlahkan_bersihnya(client, sesi, admin_headers):
    client.post('/api/shift/cash-movement', headers=admin_headers,
                json={'type': 'DROP', 'amount': 800000, 'reason': 'Setor brankas'})
    client.post('/api/shift/cash-movement', headers=admin_headers,
                json={'type': 'PAID_IN', 'amount': 200000, 'reason': 'Tambah receh'})

    isi = client.get('/api/shift/cash-movement', headers=admin_headers).get_json()
    assert len(isi['items']) == 2
    assert isi['net'] == -600000
