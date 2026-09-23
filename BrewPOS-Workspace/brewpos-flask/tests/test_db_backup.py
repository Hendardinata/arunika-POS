"""
Bagian backup/restore yang bisa diuji tanpa SQL Server sungguhan: penyaring nama
berkas (satu-satunya penghalang antara nama dari pengguna dan path di disk),
pengutipan nama basis data, dan penggabungan path lintas sistem berkas.

Jalur BACKUP/RESTORE-nya sendiri hanya bermakna diuji terhadap instance nyata --
lihat catatan di README.
"""
import pytest

from app.services import db_backup
from app.services.db_backup import DbBackupError


@pytest.mark.parametrize('nama', [
    '../../.env',
    '..\\..\\.env',
    'C:/Windows/System32/config.bak',
    '/etc/passwd',
    'backup.bak/../rahasia',
    'backup.exe',
    'backup',
    '',
    None,
])
def test_nama_berkas_berbahaya_ditolak(nama):
    """Nama berkas datang dari URL dan dari unggahan; keduanya tidak dipercaya."""
    with pytest.raises(DbBackupError):
        db_backup.path_backup(nama)


@pytest.mark.parametrize('nama', [
    'rua-caffe-20260901-085233.bak',
    'A_1.bak',
])
def test_nama_berkas_wajar_lolos_penyaring(nama):
    assert db_backup.NAMA_BERKAS.match(nama)


def test_nama_database_dikutip_bukan_disambung():
    """Nama basis data tidak bisa jadi parameter query, jadi harus aman dikutip."""
    assert db_backup._kurung('rua-caffe') == '[rua-caffe]'
    assert db_backup._kurung('nakal]; DROP DATABASE x --') == \
        '[nakal]]; DROP DATABASE x --]'


def test_path_digabung_dengan_pemisah_milik_sql_server():
    # Host Flask boleh Windows, SQL Server boleh Linux (atau sebaliknya):
    # os.path.join akan salah di salah satu arah.
    assert db_backup._gabung(r'E:\pos\backups', 'a.bak') == r'E:\pos\backups\a.bak'
    assert db_backup._gabung('/var/opt/mssql/data', 'a.bak') == '/var/opt/mssql/data/a.bak'
    assert db_backup._gabung('/var/opt/mssql/data/', 'a.bak') == '/var/opt/mssql/data/a.bak'


def test_path_diterjemahkan_ke_folder_milik_sql_server(monkeypatch):
    """Flask di Docker (/backups), SQL Server di host Windows (E:\\pos\\backups)."""
    monkeypatch.delenv('DB_BACKUP_DIR_SQL', raising=False)
    assert db_backup._path_sql('/backups/a.bak') == '/backups/a.bak'
    monkeypatch.setenv('DB_BACKUP_DIR_SQL', r'E:\pos\backups')
    assert db_backup._path_sql('/backups/a.bak') == r'E:\pos\backups\a.bak'
