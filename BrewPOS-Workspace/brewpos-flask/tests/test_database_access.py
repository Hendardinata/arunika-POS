"""
Gerbang izin halaman Manajemen Basis Data, dan alur permintaan-persetujuan
pemulihan.

Yang diuji gerbangnya, bukan BACKUP/RESTORE-nya sendiri: keduanya perintah khusus
SQL Server dan tidak berjalan di SQLite yang dipakai suite ini. Jalur-jalurnya
dipanggil sampai batas tepat sebelum SQL Server disentuh, sehingga yang tersisa
untuk gagal hanyalah keputusan izinnya.
"""
import io as _io

import bcrypt
import pytest

from app.extensions import db
from app.models.restore_request import RestoreRequest
from app.models.user import User
from app.services import login_guard, tiket_unduh

SEED_PASSWORD = '12qwaszx'


@pytest.fixture(autouse=True)
def bersihkan_rem():
    login_guard.reset_all()
    tiket_unduh.reset_all()
    yield
    login_guard.reset_all()
    tiket_unduh.reset_all()


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


def _ajukan(client, headers, **extra):
    """Ajukan permintaan dari berkas riwayat (path_backup ditambal fixture)."""
    body = {'filename': 'rua-20260101-000000.bak',
            'reason': 'Data transaksi hilang setelah listrik padam'}
    body.update(extra)
    return client.post('/api/database/restore-request', json=body, headers=headers)


@pytest.fixture
def berkas_riwayat(tmp_path, monkeypatch):
    """path_backup diarahkan ke berkas nyata di tmp, tanpa menyentuh SQL Server."""
    from app.routes import database as rute
    berkas = tmp_path / 'rua-20260101-000000.bak'
    berkas.write_bytes(b'cadangan')
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(berkas))
    return berkas


class _MesinPalsu:
    """Cukup untuk _folder_backup(): tidak menyentuh SQL Server sama sekali."""

    def connect(self):
        import contextlib
        return contextlib.nullcontext(None)

    def dispose(self):
        pass


# --- Riwayat cadangan: Superadmin saja ---------------------------------------
#
# Celah yang ditutup: kalau Owner boleh membaca daftar, ia juga bisa mengunduh
# cadangan yang dibuat Superadmin -- dan tiap .bak berisi hash sandi SEMUA akun.

@pytest.mark.parametrize('metode, jalur', [
    ('get', '/api/database/backups'),
    ('post', '/api/database/backup'),
    ('get', '/api/database/backup/rua-20260101-000000.bak'),
    ('delete', '/api/database/backup/rua-20260101-000000.bak'),
    ('post', '/api/database/backup/rua-20260101-000000.bak/tiket'),
])
def test_owner_tidak_bisa_menyentuh_riwayat(client, owner_headers, metode, jalur):
    res = getattr(client, metode)(jalur, headers=owner_headers)
    assert res.status_code == 403, jalur
    assert 'Superadmin' in res.get_json()['error']


# --- Cadangan terakhir: Owner boleh tahu kapan, bukan apa saja ---------------

def test_cadangan_owner_masuk_riwayat_superadmin(client, owner_headers, admin_headers,
                                                 tmp_path, monkeypatch):
    """
    Cadangan yang dibuat Owner tersimpan seperti cadangan lain, dan Superadmin
    melihatnya di riwayat. Owner sendiri tetap tidak bisa membuka daftar itu --
    pemisahannya ada di MELIHAT, bukan di menyimpan.
    """
    from app.routes import database as rute
    from app.services import db_backup
    berkas = tmp_path / 'rua-20260401-120000.bak'
    berkas.write_bytes(b'cadangan-owner')
    monkeypatch.setattr(rute, 'buat_backup',
                        lambda: {'filename': 'rua-20260401-120000.bak', 'size': 14})
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(berkas))
    monkeypatch.setattr(rute, 'sapu_berkas_sementara', lambda: None)

    assert client.post('/api/database/backup-download',
                       headers=owner_headers).status_code == 201

    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu())
    monkeypatch.setattr(db_backup, 'nama_database', lambda: 'rua')

    riwayat = client.get('/api/database/backups', headers=admin_headers).get_json()
    assert [b['filename'] for b in riwayat['backups']] == ['rua-20260401-120000.bak']
    assert client.get('/api/database/backups', headers=owner_headers).status_code == 403


def test_owner_boleh_lihat_cadangan_terakhir(client, owner_headers, tmp_path, monkeypatch):
    """
    Owner berhak tahu kapan tokonya terakhir dicadangkan. Yang dibuka cuma
    keterangan satu baris -- nama, ukuran, tanggal -- bukan daftarnya.
    """
    import os
    import time

    from app.services import db_backup
    # Waktu ubah disetel eksplisit: urutannya ditentukan mtime berkas, BUKAN
    # tanggal yang kebetulan tertulis di namanya. Tanpa ini keduanya lahir pada
    # detik yang sama dan urutannya jadi kebetulan.
    for nama, umur in (('rua-20260101-000000.bak', 7200), ('rua-20260305-101500.bak', 60)):
        f = tmp_path / nama
        f.write_bytes(b'x' * 10)
        saat = time.time() - umur
        os.utime(f, (saat, saat))
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu())
    monkeypatch.setattr(db_backup, 'nama_database', lambda: 'rua')

    res = client.get('/api/database/backup-latest', headers=owner_headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data['latest']['filename'] == 'rua-20260305-101500.bak'
    assert data['latest']['size'] == 10
    # Satu baris saja -- daftar lengkapnya tidak ikut terbawa.
    assert 'backups' not in data


def test_cadangan_terakhir_kosong_saat_belum_ada(client, owner_headers, tmp_path, monkeypatch):
    from app.services import db_backup
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu())
    monkeypatch.setattr(db_backup, 'nama_database', lambda: 'rua')

    res = client.get('/api/database/backup-latest', headers=owner_headers)
    assert res.status_code == 200
    assert res.get_json()['latest'] is None


def test_cadangan_terakhir_tidak_membawa_tautan_unduhan(client, owner_headers,
                                                        tmp_path, monkeypatch):
    """
    Inti pemisahannya: Owner tahu KAPAN, tapi tetap tidak bisa MENGAMBIL. Kalau
    keterangan ini sampai membawa tautan, celah yang ditutup sebelumnya terbuka
    lagi lewat pintu lain.
    """
    from app.services import db_backup
    (tmp_path / 'rua-20260101-000000.bak').write_bytes(b'x')
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu())
    monkeypatch.setattr(db_backup, 'nama_database', lambda: 'rua')

    data = client.get('/api/database/backup-latest', headers=owner_headers).get_json()
    assert 'url' not in data['latest'] and 'path' not in data['latest']
    # Dan namanya pun tidak bisa dipakai untuk mengunduh.
    nama = data['latest']['filename']
    assert client.get(f'/api/database/backup/{nama}',
                      headers=owner_headers).status_code == 403
    assert client.post(f'/api/database/backup/{nama}/tiket',
                       headers=owner_headers).status_code == 403


def test_kasir_tidak_boleh_lihat_cadangan_terakhir(client, cashier_headers):
    assert client.get('/api/database/backup-latest',
                      headers=cashier_headers).status_code == 403


def test_superadmin_tetap_pegang_riwayat(client, admin_headers):
    res = client.get('/api/database/backups', headers=admin_headers)
    # 400 = gagal di SQL Server (SQLite di suite ini), BUKAN ditolak izin.
    assert res.status_code != 403


def test_kasir_ditolak_seluruh_halaman(client, cashier_headers):
    for jalur, metode in [('/api/database/backups', 'get'),
                          ('/api/database/backup-download', 'post'),
                          ('/api/database/restore-request', 'get')]:
        res = getattr(client, metode)(jalur, headers=cashier_headers)
        assert res.status_code == 403, jalur


def test_headbar_ditolak_seluruh_halaman(client, headbar_headers):
    assert client.get('/api/database/backups', headers=headbar_headers).status_code == 403


# --- Buat & unduh: satu-satunya jalur cadangan untuk Owner -------------------

def test_owner_boleh_buat_dan_unduh(client, owner_headers):
    res = client.post('/api/database/backup-download', headers=owner_headers)
    assert res.status_code != 403


def test_buat_dan_unduh_tetap_tersimpan_di_server(client, owner_headers, tmp_path, monkeypatch):
    """
    Cadangan Admin/Owner TETAP tinggal di server setelah diunduh.

    Versi sebelumnya menghapusnya begitu terkirim. Itu keliru: kalau berkas
    unduhan si peminta hilang, tidak ada satu pun salinan yang tersisa.
    """
    from app.routes import database as rute
    berkas = tmp_path / 'rua-20260401-120000.bak'
    berkas.write_bytes(b'isi-cadangan-palsu')
    monkeypatch.setattr(rute, 'buat_backup',
                        lambda: {'filename': 'rua-20260401-120000.bak', 'size': 18})
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(berkas))
    monkeypatch.setattr(rute, 'sapu_berkas_sementara', lambda: None)

    res = client.post('/api/database/backup-download', headers=owner_headers)
    assert res.status_code == 201
    assert res.get_json()['filename'] == 'rua-20260401-120000.bak'
    unduh = client.get(res.get_json()['url'])
    assert unduh.status_code == 200
    assert unduh.data == b'isi-cadangan-palsu'
    assert berkas.exists(), 'cadangan terhapus dari server setelah diunduh'


def test_tiket_sekali_pakai(client, owner_headers, tmp_path, monkeypatch):
    from app.routes import database as rute
    palsu = tmp_path / 'rua-20260401-120000.bak'
    palsu.write_bytes(b'isi-cadangan')
    monkeypatch.setattr(rute, 'buat_backup',
                        lambda: {'filename': 'rua-20260401-120000.bak', 'size': 12})
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(palsu))
    monkeypatch.setattr(rute, 'sapu_berkas_sementara', lambda: None)

    url = client.post('/api/database/backup-download', headers=owner_headers).get_json()['url']
    # Tanpa header Authorization sama sekali -- persis seperti navigasi.
    assert client.get(url).status_code == 200
    assert client.get(url).status_code == 404


def test_tiket_kedaluwarsa_tidak_menghapus_cadangan(tmp_path, monkeypatch):
    """
    Tiket batal berarti UNDUHANNYA batal, bukan cadangannya harus hilang.
    Semua cadangan tinggal di riwayat; tiket cuma izin mengambil salinannya.
    """
    berkas = tmp_path / 'rua-20260401-120000.bak'
    berkas.write_bytes(b'x')
    token = tiket_unduh.terbitkan(str(berkas), 'rua-20260401-120000.bak')

    asli = tiket_unduh.time.time
    monkeypatch.setattr(tiket_unduh.time, 'time',
                        lambda: asli() + tiket_unduh.UMUR_DETIK + 1)
    assert tiket_unduh.tukar(token) is None
    assert berkas.exists(), 'cadangan ikut terhapus saat tiketnya kedaluwarsa'


def test_tiket_ngawur_ditolak(client):
    assert client.get('/unduh-cadangan/bukan-tiket').status_code == 404


# --- Restore: diajukan Admin/Owner, diputus Superadmin -----------------------

def test_owner_tidak_bisa_restore_langsung(client, owner_headers):
    """Jalur langsung milik Superadmin. Owner harus lewat permintaan."""
    res = client.post('/api/database/restore', headers=owner_headers,
                      json={'filename': 'apa.bak', 'confirm': 'PULIHKAN'})
    assert res.status_code == 403


def test_pengajuan_wajib_beralasan(client, owner_headers, berkas_riwayat):
    res = _ajukan(client, owner_headers, reason='iya')
    assert res.status_code == 400
    assert 'alasan' in res.get_json()['error'].lower()


def test_owner_mengajukan_lalu_menunggu(client, owner_headers, berkas_riwayat):
    res = _ajukan(client, owner_headers)
    assert res.status_code == 201
    p = res.get_json()
    assert p['status'] == 'PENDING'
    assert p['requestedBy'] == 'pemilik'
    assert p['decidedBy'] is None


def test_satu_permintaan_menggantung_saja(client, owner_headers, berkas_riwayat):
    """Antrean restore tidak masuk akal: yang kedua menimpa hasil yang pertama."""
    assert _ajukan(client, owner_headers).status_code == 201
    assert _ajukan(client, owner_headers).status_code == 409


def test_owner_tidak_bisa_menyetujui_permintaannya_sendiri(client, owner_headers, berkas_riwayat):
    """Inti pemisahannya: yang mengajukan bukan yang memutuskan."""
    pid = _ajukan(client, owner_headers).get_json()['id']
    assert client.post(f'/api/database/restore-request/{pid}/approve',
                       json={'confirm': 'PULIHKAN'}, headers=owner_headers).status_code == 403
    assert client.post(f'/api/database/restore-request/{pid}/reject',
                       json={}, headers=owner_headers).status_code == 403


def test_owner_boleh_membatalkan_permintaannya(client, owner_headers, berkas_riwayat):
    pid = _ajukan(client, owner_headers).get_json()['id']
    res = client.delete(f'/api/database/restore-request/{pid}', headers=owner_headers)
    assert res.status_code == 200
    assert res.get_json()['status'] == 'CANCELLED'
    # Setelah dibatalkan, permintaan baru boleh diajukan lagi.
    assert _ajukan(client, owner_headers).status_code == 201


def test_superadmin_menolak_dengan_catatan(client, owner_headers, admin_headers, berkas_riwayat):
    pid = _ajukan(client, owner_headers).get_json()['id']
    res = client.post(f'/api/database/restore-request/{pid}/reject',
                      json={'note': 'Pakai cadangan kemarin saja'}, headers=admin_headers)
    assert res.status_code == 200
    p = res.get_json()
    assert p['status'] == 'REJECTED'
    assert p['decidedBy'] == 'superadmin'
    assert p['decisionNote'] == 'Pakai cadangan kemarin saja'


def test_persetujuan_tetap_menuntut_konfirmasi_ketikan(client, owner_headers,
                                                       admin_headers, berkas_riwayat):
    """Pengaman terakhir supaya tombol Setujui tidak tertekan tanpa sengaja."""
    pid = _ajukan(client, owner_headers).get_json()['id']
    res = client.post(f'/api/database/restore-request/{pid}/approve',
                      json={}, headers=admin_headers)
    assert res.status_code == 400
    assert 'PULIHKAN' in res.get_json()['error']


def test_persetujuan_sah_lolos_ke_lapisan_basis_data(client, owner_headers,
                                                     admin_headers, berkas_riwayat):
    """
    Dengan konfirmasi benar, permintaan lolos gerbang dan baru gagal di RESTORE
    (SQLite di suite ini) -- itulah yang membuktikan izinnya diterima.
    """
    pid = _ajukan(client, owner_headers).get_json()['id']
    res = client.post(f'/api/database/restore-request/{pid}/approve',
                      json={'confirm': 'PULIHKAN'}, headers=admin_headers)
    assert res.status_code == 400
    assert 'Superadmin' not in res.get_json()['error']


def test_permintaan_yang_sudah_diputus_tidak_bisa_diputus_lagi(client, owner_headers,
                                                               admin_headers, berkas_riwayat):
    pid = _ajukan(client, owner_headers).get_json()['id']
    assert client.post(f'/api/database/restore-request/{pid}/reject',
                       json={}, headers=admin_headers).status_code == 200
    assert client.post(f'/api/database/restore-request/{pid}/approve',
                       json={'confirm': 'PULIHKAN'}, headers=admin_headers).status_code == 404


def test_pemohon_hanya_melihat_permintaannya_sendiri(client, owner_headers,
                                                     admin_headers, berkas_riwayat, app):
    _ajukan(client, owner_headers)
    with app.app_context():
        db.session.add(RestoreRequest(requestedBy=None, sourceType='HISTORY',
                                      filename='punya-orang-lain.bak',
                                      storedName='punya-orang-lain.bak',
                                      reason='bukan milik pemilik', status='REJECTED'))
        db.session.commit()

    milik_owner = client.get('/api/database/restore-request', headers=owner_headers).get_json()
    assert milik_owner['canApprove'] is False
    assert all(r['requestedBy'] == 'pemilik' for r in milik_owner['requests'])

    milik_sa = client.get('/api/database/restore-request', headers=admin_headers).get_json()
    assert milik_sa['canApprove'] is True
    assert len(milik_sa['requests']) >= 2


def test_unggahan_menunggu_lalu_dibuang_saat_ditolak(client, owner_headers,
                                                     admin_headers, tmp_path, monkeypatch):
    """
    Berkas unggahan menunggu di server sampai diputus. Begitu ditolak ia harus
    hilang -- isinya seluruh basis data.
    """
    from app.routes import database as rute
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(tmp_path / n))

    data = {'file': (_io.BytesIO(b'cadangan-unggahan'), 'punyaku.bak'),
            'reason': 'Uji berkas unggahan menunggu keputusan'}
    res = client.post('/api/database/restore-request', data=data, headers=owner_headers,
                      content_type='multipart/form-data')
    assert res.status_code == 201
    pid = res.get_json()['id']

    tersimpan = list(tmp_path.glob('pending-*.bak'))
    assert len(tersimpan) == 1, 'berkas unggahan tidak tersimpan menunggu keputusan'

    assert client.post(f'/api/database/restore-request/{pid}/reject',
                       json={}, headers=admin_headers).status_code == 200
    assert not tersimpan[0].exists(), 'berkas unggahan tertinggal setelah ditolak'


# --- Berkas yang menunggu keputusan hidup dengan aturannya sendiri ------------

def test_berkas_menunggu_tidak_muncul_di_riwayat(tmp_path, monkeypatch):
    """pending-* disembunyikan dari riwayat, seperti berkas kerja lain."""
    from app.services import db_backup
    (tmp_path / 'rua-20260101-000000.bak').write_bytes(b'x')
    (tmp_path / 'pending-abc123.bak').write_bytes(b'x')
    (tmp_path / 'unduh-rua.bak').write_bytes(b'x')
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu())
    monkeypatch.setattr(db_backup, 'nama_database', lambda: 'rua')
    nama = [b['filename'] for b in db_backup.daftar_backup()['backups']]
    assert nama == ['rua-20260101-000000.bak']


def test_berkas_menunggu_tidak_ikut_disapu(tmp_path, monkeypatch):
    """
    Penyapu satu jam membuang berkas kerja. Berkas yang menunggu keputusan TIDAK
    boleh ikut -- kalau ikut, permintaan yang diajukan sore hari sudah kehilangan
    berkasnya sebelum Superadmin sempat melihatnya besok pagi.
    """
    import os
    import time

    from app.services import db_backup
    lama = time.time() - 7200
    for nama in ('unduh-lama.bak', 'pending-lama.bak'):
        f = tmp_path / nama
        f.write_bytes(b'x')
        os.utime(f, (lama, lama))
    monkeypatch.setenv('DB_BACKUP_DIR', str(tmp_path))
    monkeypatch.setattr(db_backup, '_mesin_master', lambda: _MesinPalsu())

    db_backup.sapu_berkas_sementara()
    assert not (tmp_path / 'unduh-lama.bak').exists(), 'berkas kerja tidak disapu'
    assert (tmp_path / 'pending-lama.bak').exists(), 'berkas menunggu keputusan ikut tersapu'


def test_berkas_kerja_sementara_tidak_bisa_diunduh(client, admin_headers):
    for nama in ('unduh-rua-20260101-000000.bak', 'upload-1234.bak', 'pending-abc.bak'):
        res = client.get(f'/api/database/backup/{nama}', headers=admin_headers)
        assert res.status_code == 404, nama


def test_riwayat_tidak_dihapus_setelah_diunduh(client, admin_headers, tmp_path, monkeypatch):
    """Riwayat itu arsip: mengunduhnya tidak boleh menghapusnya."""
    from app.routes import database as rute
    arsip = tmp_path / 'rua-20260101-000000.bak'
    arsip.write_bytes(b'arsip')
    monkeypatch.setattr(rute, 'path_backup', lambda n, harus_ada=True: str(arsip))

    res = client.post('/api/database/backup/rua-20260101-000000.bak/tiket',
                      headers=admin_headers)
    assert res.status_code == 201
    unduh = client.get(res.get_json()['url'])
    assert unduh.status_code == 200 and unduh.data == b'arsip'
    assert arsip.exists(), 'berkas riwayat ikut terhapus'
