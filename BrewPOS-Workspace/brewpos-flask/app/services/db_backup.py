"""
Backup dan restore basis data SQL Server.

Memakai BACKUP/RESTORE bawaan SQL Server, bukan dump baris per baris ke JSON.
Alasannya: dump JSON harus tahu urutan foreign key, harus mengurus IDENTITY_INSERT
untuk tiap tabel, dan diam-diam ketinggalan setiap kali ada model baru. Berkas .bak
tidak punya satu pun masalah itu -- isinya seluruh basis data apa adanya, dan
memulihkannya adalah satu perintah.

Konsekuensinya: berkas .bak ditulis oleh SQL Server, bukan oleh Flask. Jadi
foldernya harus bisa ditulis layanan SQL Server DAN dibaca proses Flask -- dan
folder backup bawaan SQL Server tidak memenuhi syarat kedua: ia berada di dalam
Program Files dan proses Flask biasa ditolak membacanya. Maka dipakai folder
`backups/` milik aplikasi ini, lalu akun layanan SQL Server diberi izin tulis ke
sana sekali di awal. DB_BACKUP_DIR di .env menimpa pilihan folder ini.
"""

import os
import re
import subprocess
from datetime import datetime

from flask import current_app
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.config import BASE_DIR
from app.extensions import db

NAMA_BERKAS = re.compile(r'^[A-Za-z0-9._-]+\.bak$')

# Berkas kerja yang tidak pernah jadi bagian dari riwayat cadangan: hasil "buat
# & unduh" milik Admin/Owner (dihapus begitu terkirim) dan berkas unggahan yang
# sedang menunggu dipulihkan. Keduanya numpang di folder yang sama karena SQL
# Server hanya bisa membaca-tulis di sana.
AWALAN_SEMENTARA = ('unduh-', 'upload-')


class DbBackupError(Exception):
    """Kegagalan yang pesannya memang untuk dibaca pengguna."""


def _kurung(nama):
    """Nama database tidak bisa jadi parameter query, jadi harus dikutip sendiri."""
    return '[' + str(nama).replace(']', ']]') + ']'


def _url():
    url = make_url(current_app.config['SQLALCHEMY_DATABASE_URI'])
    if not url.drivername.startswith('mssql'):
        raise DbBackupError(
            'Backup/restore bawaan hanya tersedia untuk SQL Server '
            f'(DATABASE_URL sekarang: {url.drivername}).')
    if not url.database:
        raise DbBackupError('DATABASE_URL tidak menyebut nama basis data.')
    return url


def nama_database():
    return _url().database


def _mesin_master():
    """
    Koneksi terpisah ke master. Dua alasan: RESTORE tidak boleh dijalankan dari
    koneksi ke basis data yang sedang dipulihkan, dan BACKUP/RESTORE tidak boleh
    berada di dalam transaksi -- maka AUTOCOMMIT.
    """
    return create_engine(_url().set(database='master'),
                         isolation_level='AUTOCOMMIT', pool_pre_ping=True)


def _jalankan_tuntas(conn, sql, params=None):
    """
    Jalankan BACKUP/RESTORE lewat kursor ODBC langsung, lalu habiskan seluruh
    result set-nya.

    Keduanya melaporkan kemajuannya sebagai deretan result set, dan pekerjaannya
    baru benar-benar selesai setelah semuanya diambil. SQLAlchemy menutup kursor
    begitu perintah dianggap "tidak mengembalikan baris", dan ODBC membatalkan
    batch yang belum selesai itu: tidak ada galat, tidak ada berkas, seolah
    perintahnya berhasil. Persis itu yang terjadi sebelum helper ini ada --
    "Buat Backup" selalu melapor sukses tanpa pernah menghasilkan satu pun .bak.
    """
    kursor = conn.connection.cursor()
    try:
        if params:
            kursor.execute(sql, params)
        else:
            kursor.execute(sql)
        while kursor.nextset():
            pass
    finally:
        kursor.close()


def _izinkan_sql_server_menulis(conn, folder):
    """
    Beri akun layanan SQL Server izin tulis ke folder backup.

    Folder ini dibuat proses Flask, jadi SQL Server tidak punya akses ke sana dan
    BACKUP gagal dengan "Operating system error 5 (Access is denied)". Karena
    proses inilah pemilik foldernya, izin bisa diberikan tanpa hak administrator.
    Ditandai dengan berkas penanda supaya icacls tidak dijalankan tiap permintaan.
    """
    penanda = os.path.join(folder, '.akses-sqlserver')
    if os.path.exists(penanda) or os.name != 'nt':
        return
    try:
        akun = conn.exec_driver_sql(
            "SELECT service_account FROM sys.dm_server_services "
            "WHERE servicename LIKE 'SQL Server (%'").scalar()
        if akun:
            subprocess.run(['icacls', folder, '/grant', f'{akun}:(OI)(CI)M'],
                           capture_output=True, timeout=30)
        with open(penanda, 'w', encoding='utf-8') as f:
            f.write(akun or 'akun layanan tidak terbaca')
    except Exception as e:
        # Bukan alasan menggagalkan permintaan: kalau izinnya ternyata sudah ada,
        # BACKUP tetap jalan. Kalau tidak, pesan galat BACKUP yang menjelaskannya.
        print(f'[DbBackup] Gagal memberi izin folder ke SQL Server: {e}')


def _folder_backup(conn):
    """Folder tempat .bak disimpan. DB_BACKUP_DIR menang; bawaannya backups/."""
    folder = os.getenv('DB_BACKUP_DIR') or os.path.join(BASE_DIR, 'backups')
    os.makedirs(folder, exist_ok=True)
    _izinkan_sql_server_menulis(conn, folder)
    return folder


def _gabung(folder, berkas):
    """
    Path digabung dengan pemisah milik SQL Server, bukan milik host Flask.
    Keduanya hampir selalu mesin yang sama, tapi os.path.join di Windows akan
    menghasilkan '\\' untuk folder Linux '/var/opt/mssql/data' -- dan SQL Server
    menolaknya.
    """
    pemisah = '\\' if '\\' in folder else '/'
    return folder.rstrip('\\/') + pemisah + berkas


def daftar_backup():
    """Berkas .bak yang ada di folder backup, terbaru dulu."""
    mesin = _mesin_master()
    try:
        with mesin.connect() as conn:
            folder = _folder_backup(conn)
    finally:
        mesin.dispose()

    hasil = []
    try:
        for nama in os.listdir(folder):
            if not NAMA_BERKAS.match(nama) or nama.startswith(AWALAN_SEMENTARA):
                continue
            try:
                stat = os.stat(os.path.join(folder, nama))
            except OSError:
                continue
            hasil.append({
                'filename': nama,
                'size': stat.st_size,
                'createdAt': datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds'),
            })
    except OSError as e:
        # SQL Server bisa menulis ke sana, proses Flask belum tentu.
        raise DbBackupError(
            f'Folder backup tidak bisa dibaca aplikasi ({folder}): {e}. '
            'Setel DB_BACKUP_DIR ke folder yang bisa diakses keduanya.')

    hasil.sort(key=lambda b: b['createdAt'], reverse=True)
    return {'directory': folder, 'database': nama_database(), 'backups': hasil}


def _folder():
    mesin = _mesin_master()
    try:
        with mesin.connect() as conn:
            return _folder_backup(conn)
    finally:
        mesin.dispose()


def path_backup(nama_berkas, harus_ada=True):
    """Path lengkap satu berkas backup, setelah namanya dipastikan aman."""
    if not NAMA_BERKAS.match(nama_berkas or ''):
        raise DbBackupError('Nama berkas backup tidak valid (harus berakhiran .bak).')
    penuh = os.path.join(_folder(), nama_berkas)
    if harus_ada and not os.path.isfile(penuh):
        raise DbBackupError(f'Berkas {nama_berkas} tidak ada di folder backup.')
    return penuh


def sapu_berkas_sementara():
    """
    Buang sisa berkas kerja yang lebih tua dari satu jam.

    Berkas "buat & unduh" dihapus begitu terkirim, tapi kalau proses mati di
    tengah pengiriman berkas itu tertinggal -- dan isinya seluruh basis data.
    Disapu di awal tiap permintaan sejenis supaya sisa itu tidak menumpuk diam-
    diam di server. Ambang satu jam supaya tidak menghapus berkas milik
    permintaan lain yang sedang berjalan saat ini.
    """
    try:
        folder = _folder()
    except DbBackupError:
        return
    batas = datetime.now().timestamp() - 3600
    try:
        for nama in os.listdir(folder):
            if not nama.startswith(AWALAN_SEMENTARA):
                continue
            penuh = os.path.join(folder, nama)
            try:
                if os.path.getmtime(penuh) < batas:
                    os.remove(penuh)
            except OSError:
                pass          # dipakai proses lain, atau sudah hilang duluan
    except OSError:
        pass


def buat_backup(sementara=False):
    """
    BACKUP DATABASE penuh. Mengembalikan metadata berkas yang dihasilkan.

    sementara=True menamainya dengan awalan yang membuatnya TIDAK muncul di
    riwayat cadangan. Dipakai jalur "buat & unduh": berkasnya hanya numpang
    lewat, dikirim ke pengunduh lalu dihapus.
    """
    dbname = nama_database()
    aman = re.sub(r'[^A-Za-z0-9_-]', '_', dbname)
    awalan = 'unduh-' if sementara else ''
    berkas = f"{awalan}{aman}-{datetime.now():%Y%m%d-%H%M%S}.bak"

    mesin = _mesin_master()
    try:
        with mesin.connect() as conn:
            folder = _folder_backup(conn)
            # INIT + FORMAT: berkas baru tiap kali, bukan menambahkan set backup
            # ke berkas lama -- yang membuat ukurannya membengkak diam-diam.
            _jalankan_tuntas(
                conn,
                f"BACKUP DATABASE {_kurung(dbname)} TO DISK = ? "
                f"WITH INIT, FORMAT, NAME = ?, DESCRIPTION = ?",
                (_gabung(folder, berkas), f'{dbname} full backup',
                 f'ARUNIKA POS {datetime.now():%d/%m/%Y %H:%M}'),
            )
    except DbBackupError:
        raise
    except Exception as e:
        raise DbBackupError(f'BACKUP gagal: {e}')
    finally:
        mesin.dispose()

    try:
        ukuran = os.path.getsize(os.path.join(folder, berkas))
    except OSError:
        ukuran = None   # SQL Server menulisnya; Flask belum tentu bisa melihatnya
    return {'filename': berkas, 'size': ukuran, 'directory': folder}


def hapus_backup(nama_berkas):
    try:
        os.remove(path_backup(nama_berkas))
    except OSError as e:
        raise DbBackupError(f'Gagal menghapus {nama_berkas}: {e}')


def _klausa_move(conn, dbname, sumber):
    """
    Pasangkan berkas di dalam .bak dengan lokasi berkas basis data yang sekarang.

    Tanpa ini, backup yang dibuat di mesin lain (atau sebelum instance dipindah)
    gagal dipulihkan: RESTORE mencoba menulis ke path yang tertulis di dalam
    backup, dan path itu belum tentu ada di sini.
    """
    isi = conn.exec_driver_sql(
        "RESTORE FILELISTONLY FROM DISK = ?", (sumber,)).mappings().all()
    if not isi:
        raise DbBackupError('Berkas backup tidak berisi daftar berkas basis data.')

    sekarang = conn.exec_driver_sql(
        "SELECT type_desc, physical_name FROM sys.master_files "
        "WHERE database_id = DB_ID(?) ORDER BY file_id", (dbname,)).all()
    tujuan = {}
    for jenis, path in sekarang:
        tujuan.setdefault(str(jenis).upper(), []).append(path)

    klausa, params = [], []
    dipakai = {}
    for baris in isi:
        jenis = 'LOG' if str(baris['Type']).upper() == 'L' else 'ROWS'
        antre = tujuan.get(jenis) or []
        ke = dipakai.get(jenis, 0)
        if ke < len(antre):
            path = antre[ke]
        else:
            # Backup punya lebih banyak berkas daripada basis data sekarang:
            # taruh di samping berkas yang ada, dinamai dari nama logisnya.
            dasar = (antre or tujuan.get('ROWS') or [''])[0]
            akhiran = '_log.ldf' if jenis == 'LOG' else '.mdf'
            path = _gabung(os.path.dirname(dasar) or '.',
                           f"{baris['LogicalName']}{akhiran}")
        dipakai[jenis] = ke + 1
        klausa.append('MOVE ? TO ?')
        params.extend([baris['LogicalName'], path])

    return ', '.join(klausa), params


def pulihkan_backup(sumber):
    """
    RESTORE dari berkas .bak yang sudah berada di folder backup.

    `sumber` harus path yang bisa dibaca SQL Server (bukan berkas sementara milik
    Flask), karena SQL Server yang membacanya, bukan proses ini.
    """
    dbname = nama_database()
    mesin = _mesin_master()
    single_user = False
    try:
        with mesin.connect() as conn:
            # Diperiksa SEBELUM koneksi lain diputus: berkas rusak atau salah
            # unggah tidak boleh sampai menutup POS untuk semua orang lebih dulu.
            try:
                header = conn.exec_driver_sql(
                    "RESTORE HEADERONLY FROM DISK = ?", (sumber,)).mappings().first()
            except Exception as e:
                raise DbBackupError(
                    f'Berkas ini bukan backup SQL Server yang bisa dibaca: {e}')
            if not header:
                raise DbBackupError('Berkas backup kosong atau tidak berisi set backup.')
            asal = header.get('DatabaseName')

            move, params_move = _klausa_move(conn, dbname, sumber)

            # Kolam koneksi aplikasi masih memegang basis data ini. Tanpa dilepas,
            # SINGLE_USER memutusnya di tengah jalan dan meninggalkan koneksi
            # rusak di kolam.
            db.session.remove()
            db.engine.dispose()

            conn.exec_driver_sql(
                f"ALTER DATABASE {_kurung(dbname)} SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            single_user = True

            _jalankan_tuntas(
                conn,
                f"RESTORE DATABASE {_kurung(dbname)} FROM DISK = ? "
                f"WITH REPLACE, RECOVERY, {move}",
                tuple([sumber] + params_move),
            )

            conn.exec_driver_sql(f"ALTER DATABASE {_kurung(dbname)} SET MULTI_USER")
            single_user = False
        return {'database': dbname, 'restoredFrom': asal}
    except DbBackupError:
        raise
    except Exception as e:
        raise DbBackupError(f'RESTORE gagal: {e}')
    finally:
        if single_user:
            # Basis data tidak boleh ditinggal SINGLE_USER: kalau iya, POS mati
            # total sampai ada yang membukanya kembali lewat SSMS.
            try:
                with mesin.connect() as conn:
                    conn.exec_driver_sql(
                        f"ALTER DATABASE {_kurung(dbname)} SET MULTI_USER")
            except Exception as e:
                print(f'[DbBackup] GAGAL mengembalikan {dbname} ke MULTI_USER: {e}')
        mesin.dispose()
