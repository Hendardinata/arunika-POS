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


# --- Riwayat cadangan: Superadmin saja ---------------------------------------
#
# Inilah celah yang ditutup: kalau Owner boleh membaca daftar, ia juga bisa
# mengunduh cadangan yang dibuat Superadmin -- dan tiap .bak berisi hash sandi
# SEMUA akun, termasuk Superadmin sendiri.

@pytest.mark.parametrize('metode, jalur', [
    ('get', '/api/database/backups'),
    ('post', '/api/database/backup'),
    ('get', '/api/database/backup/rua-20260101-000000.bak'),
    ('delete', '/api/database/backup/rua-20260101-000000.bak'),
])
def test_owner_tidak_bisa_menyentuh_riwayat(client, owner_headers, metode, jalur):
    res = getattr(client, metode)(jalur, headers=owner_headers)
    assert res.status_code == 403, jalur
    assert 'Superadmin' in res.get_json()['error']


def test_superadmin_tetap_pegang_riwayat(client, admin_headers):
    res = client.get('/api/database/backups', headers=admin_headers)
    # 400 = gagal di SQL Server (SQLite di suite ini), BUKAN ditolak izin.
    assert res.status_code != 403


# --- Buat & unduh: satu-satunya jalur cadangan untuk Owner -------------------

def test_owner_boleh_buat_dan_unduh(client, owner_headers):
    """Lolos gerbang izin; gagal berikutnya di SQL Server, bukan di izin."""
    res = client.post('/api/database/backup-download', headers=owner_headers)
    assert res.status_code != 403


def test_kasir_tidak_boleh_buat_dan_unduh(client, cashier_headers):
    res = client.post('/api/database/backup-download', headers=cashier_headers)
    assert res.status_code == 403


def test_buat_dan_unduh_tidak_meninggalkan_berkas(client, owner_headers, tmp_path, monkeypatch):
    """
    Regresi. Versi pertama memakai send_file + call_on_close dan berkasnya
    TERTINGGAL: tiga .bak 12 MB menumpuk setelah tiga permintaan, masing-masing
    berisi seluruh basis data termasuk hash sandi. Sekarang berkasnya dihapus
    sebelum respons dikirim, jadi tidak ada urutan kejadian yang menyisakannya.
    """
    from app.routes import database as rute

    palsu = tmp_path / 'unduh-uji.bak'
    palsu.write_bytes(b'isi-cadangan-palsu')
    monkeypatch.setattr(rute, 'buat_backup', lambda sementara=False: {'filename': 'unduh-uji.bak'})
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(palsu))
    monkeypatch.setattr(rute, 'sapu_berkas_sementara', lambda: None)

    res = client.post('/api/database/backup-download', headers=owner_headers)
    assert res.status_code == 200
    assert res.data == b'isi-cadangan-palsu'
    assert 'unduh-' not in res.headers.get('Content-Disposition', '')
    assert not palsu.exists(), 'berkas cadangan tertinggal di server'


def test_berkas_kerja_sementara_tidak_bisa_diunduh(client, admin_headers):
    """
    Hasil "buat & unduh" numpang di folder yang sama sebelum dihapus. Selama
    jeda itu ia tidak boleh bisa diambil lewat alamat unduhan riwayat.
    """
    for nama in ('unduh-rua-20260101-000000.bak', 'upload-1234.bak'):
        res = client.get(f'/api/database/backup/{nama}', headers=admin_headers)
        assert res.status_code == 404, nama


def test_berkas_sementara_tidak_muncul_di_riwayat(tmp_path, monkeypatch):
    """daftar_backup() menyaring berkas kerja, bukan hanya menamainya berbeda."""
    from app.services import db_backup
    (tmp_path / 'rua-20260101-000000.bak').write_bytes(b'x')
    (tmp_path / 'unduh-rua-20260102-000000.bak').write_bytes(b'x')
    (tmp_path / 'upload-999.bak').write_bytes(b'x')
    # DB_BACKUP_DIR menang atas folder bawaan -- tanpa ini tesnya membaca folder
    # cadangan sungguhan milik mesin ini.
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu(str(tmp_path)))
    monkeypatch.setattr(db_backup, 'nama_database', lambda: 'rua')
    nama = [b['filename'] for b in db_backup.daftar_backup()['backups']]
    assert nama == ['rua-20260101-000000.bak']


class _MesinPalsu:
    """Cukup untuk _folder_backup(): tidak menyentuh SQL Server sama sekali."""
    def __init__(self, folder):
        self._folder = folder

    def connect(self):
        import contextlib
        return contextlib.nullcontext(None)

    def dispose(self):
        pass


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
