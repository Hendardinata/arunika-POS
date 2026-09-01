"""
Gerbang izin halaman Manajemen Basis Data.

Yang diuji di sini gerbangnya, bukan BACKUP/RESTORE-nya sendiri: keduanya
perintah khusus SQL Server dan tidak berjalan di SQLite yang dipakai suite ini.
Jalur restore sengaja dipanggil sampai batas tepat sebelum SQL Server disentuh,
sehingga yang tersisa untuk gagal hanyalah keputusan izinnya.
"""
import bcrypt
import pytest

from app.extensions import db
from app.models.user import User
from app.services import login_guard

SEED_PASSWORD = '12qwaszx'


@pytest.fixture(autouse=True)
def bersihkan_rem():
    login_guard.reset_all()
    yield
    login_guard.reset_all()


def _login(client, username, password=SEED_PASSWORD):
    res = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200, res.get_json()
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


@pytest.fixture
def owner_headers(client, app):
    """
    Peran OWNER sungguhan. Akun 'owner' bawaan seeder berperan ADMIN (levelnya
    sama), jadi ia tidak membuktikan apa pun tentang OWNER itu sendiri.
    """
    with app.app_context():
        db.session.add(User(
            username='pemilik',
            password=bcrypt.hashpw(SEED_PASSWORD.encode(), bcrypt.gensalt()).decode(),
            role='OWNER'))
        db.session.commit()
    return _login(client, 'pemilik')


def _restore(client, headers, **extra):
    body = {'filename': 'tidak-ada.bak', 'confirm': 'PULIHKAN'}
    body.update(extra)
    return client.post('/api/database/restore', json=body, headers=headers)


# --- Membuat & melihat cadangan: Admin/Owner ke atas -------------------------

def test_owner_boleh_melihat_daftar_cadangan(client, owner_headers):
    """Owner memegang datanya sendiri; melihat daftar cadangan bukan hak istimewa."""
    res = client.get('/api/database/backups', headers=owner_headers)
    # 400 = gagal di SQL Server (SQLite di suite ini), BUKAN ditolak izin.
    assert res.status_code != 403


def test_kasir_ditolak_seluruh_halaman(client, cashier_headers):
    for jalur, metode in [('/api/database/backups', 'get'),
                          ('/api/database/backup', 'post')]:
        res = getattr(client, metode)(jalur, headers=cashier_headers)
        assert res.status_code == 403, jalur


def test_headbar_ditolak_seluruh_halaman(client, headbar_headers):
    res = client.get('/api/database/backups', headers=headbar_headers)
    assert res.status_code == 403


# --- Restore: wajib konfirmasi Superadmin ------------------------------------

def test_owner_tanpa_konfirmasi_ditolak(client, owner_headers):
    res = _restore(client, owner_headers)
    assert res.status_code == 403
    assert 'Superadmin' in res.get_json()['error']


def test_owner_dengan_sandi_superadmin_salah_ditolak(client, owner_headers):
    res = _restore(client, owner_headers,
                   superadminUsername='superadmin', superadminPassword='salah')
    assert res.status_code == 403
    assert res.get_json()['error'] == 'Konfirmasi Superadmin tidak valid.'


def test_konfirmasi_memakai_akun_bukan_superadmin_ditolak(client, owner_headers):
    """Sandi benar tapi perannya Owner -- tetap bukan persetujuan Superadmin."""
    res = _restore(client, owner_headers,
                   superadminUsername='pemilik', superadminPassword=SEED_PASSWORD)
    assert res.status_code == 403
    assert res.get_json()['error'] == 'Konfirmasi Superadmin tidak valid.'


def test_superadmin_sendiri_tetap_harus_mengetik_sandi(client, admin_headers):
    """
    Sesi Superadmin saja tidak cukup. Kalau cukup, sesi yang tertinggal terbuka
    di perangkat lain sudah bisa menghapus isi toko.
    """
    res = _restore(client, admin_headers)
    assert res.status_code == 403
    assert 'Superadmin' in res.get_json()['error']


def test_konfirmasi_sah_lolos_gerbang_izin(client, owner_headers):
    """
    Dengan konfirmasi yang benar, permintaan lolos gerbang dan baru gagal di
    lapisan basis data -- itulah yang membuktikan izinnya diterima.
    """
    res = _restore(client, owner_headers,
                   superadminUsername='superadmin', superadminPassword=SEED_PASSWORD)
    assert res.status_code == 400
    assert 'Superadmin' not in res.get_json()['error']


def test_tebakan_beruntun_akhirnya_tertahan(client, owner_headers):
    """
    Tanpa rem, endpoint ini jadi alat penebak sandi Superadmin: tidak lewat
    /api/auth/login, jadi tidak satu pun percobaannya tercatat sebagai gagal login.
    """
    for _ in range(login_guard.MAX_FAILURES):
        assert _restore(client, owner_headers, superadminUsername='superadmin',
                        superadminPassword='salah').status_code == 403

    tertahan = _restore(client, owner_headers,
                        superadminUsername='superadmin', superadminPassword='salah')
    assert tertahan.status_code == 429

    # Sandi yang benar pun ikut tertahan selama jendela remnya berjalan.
    assert _restore(client, owner_headers, superadminUsername='superadmin',
                    superadminPassword=SEED_PASSWORD).status_code == 429


def test_konfirmasi_lewat_unggahan_juga_diperiksa(client, owner_headers):
    """Jalur multipart tidak boleh jadi pintu belakang yang melewati konfirmasi."""
    import io as _io
    data = {'file': (_io.BytesIO(b'bukan-bak'), 'cadangan.bak'), 'confirm': 'PULIHKAN'}
    res = client.post('/api/database/restore', data=data, headers=owner_headers,
                      content_type='multipart/form-data')
    assert res.status_code == 403
    assert 'Superadmin' in res.get_json()['error']
