"""
Manajemen basis data: unduh backup dan pulihkan dari backup.

Dua tingkat izin, karena bobot kedua tindakan ini jauh berbeda:

- Membuat, mengunduh, dan menghapus cadangan: Admin/Owner ke atas. Ini data
  tokonya sendiri, dan pemiliknya berhak memegang salinannya.
- Memulihkan: WAJIB disetujui Superadmin, siapa pun yang menekan tombolnya --
  Owner sekalipun, dan Superadmin sendiri pun tetap harus mengetik ulang
  sandinya. Restore menimpa seluruh basis data dan tidak bisa dibatalkan, jadi
  tidak cukup bersandar pada "yang sedang login siapa": sesi yang tertinggal
  terbuka di perangkat lain tidak boleh cukup untuk menghapus isi toko.

Yang perlu diketahui pemberi izin: berkas .bak berisi SELURUH isi basis data,
termasuk hash sandi setiap akun.
"""

import os

import bcrypt
from flask import Blueprint, jsonify, request, send_file

from app.extensions import db
from app.middleware.auth import (ROLE_LEVELS, get_current_user_id,
                                 has_role_level)
from app.models.user import User
from app.services import login_guard
from app.services.db_backup import (DbBackupError, buat_backup, daftar_backup,
                                    hapus_backup, path_backup, pulihkan_backup)
from app.services.system_logger import log_activity

database_bp = Blueprint('database', __name__, url_prefix='/api/database')

# Berkas .bak jauh melampaui MAX_CONTENT_LENGTH global (16 MB, ukuran untuk foto
# nota). Batasnya dinaikkan per-request saja, supaya jalur unggah lain tetap
# terjaga di angka kecilnya.
MAKS_UNGGAH = 4 * 1024 * 1024 * 1024   # 4 GB


@database_bp.before_request
def _gerbang():
    if not has_role_level(ROLE_LEVELS['ADMIN']):
        return jsonify({
            'error': 'Manajemen basis data memerlukan otorisasi Admin/Owner'
        }), 403
    return None


def _izin_superadmin(data):
    """
    Verifikasi sandi Superadmin yang diketikkan untuk menyetujui restore.

    Mengembalikan (nama_superadmin, None) bila sah, atau (None, respons_galat).

    Yang dikembalikan sengaja STRING, bukan objek User: pemanggilnya mencatat
    nama itu setelah restore selesai, dan saat itu sesi ORM sudah dilepas serta
    basis datanya sudah diganti -- membaca atribut dari objek yang terlepas akan
    meledak atau, lebih buruk, diam-diam menanyakannya ke basis data yang baru.

    Memakai rem yang sama dengan halaman login. Tanpa itu endpoint ini jadi alat
    penebak sandi Superadmin yang nyaman: pemegang token Owner bisa mencoba
    tanpa batas, dan tidak satu pun kegagalannya muncul sebagai kegagalan login
    karena jalurnya bukan /api/auth/login.

    Pesan galatnya sengaja sama untuk semua sebab -- username tidak ada, bukan
    Superadmin, atau sandi salah. Membedakannya sama dengan memberi tahu penebak
    bagian mana yang sudah benar.
    """
    nama = (data.get('superadminUsername') or '').strip()
    sandi = data.get('superadminPassword') or ''
    if not nama or not sandi:
        return None, (jsonify({
            'error': 'Restore harus disetujui Superadmin. Isi username dan sandi Superadmin.'
        }), 403)

    tertahan = login_guard.seconds_until_unlocked(nama)
    if tertahan:
        return None, (jsonify({
            'error': f'Terlalu banyak percobaan. Coba lagi dalam {tertahan // 60 + 1} menit.'
        }), 429)

    user = User.query.filter(db.func.lower(User.username) == nama.lower()).first()
    sah = False
    if user and (user.role or '').upper() == 'SUPERADMIN':
        try:
            sah = bcrypt.checkpw(sandi.encode('utf-8'), user.password.encode('utf-8'))
        except (ValueError, TypeError):
            sah = False   # hash rusak diperlakukan sebagai gagal, bukan galat 500

    if not sah:
        login_guard.record_failure(nama)
        return None, (jsonify({'error': 'Konfirmasi Superadmin tidak valid.'}), 403)

    login_guard.clear(nama)
    return user.username, None


@database_bp.route('/backups', methods=['GET'])
def list_backups():
    try:
        return jsonify(daftar_backup())
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400


@database_bp.route('/backup', methods=['POST'])
def create_backup():
    try:
        info = buat_backup()
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400
    log_activity('DB_BACKUP', get_current_user_id(),
                 f"Membuat backup {info['filename']}", 'Database', None)
    return jsonify(info), 201


@database_bp.route('/backup/<path:filename>', methods=['GET'])
def download_backup(filename):
    try:
        penuh = path_backup(filename)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 404
    log_activity('DB_BACKUP_DOWNLOAD', get_current_user_id(),
                 f"Mengunduh backup {filename}", 'Database', None)
    return send_file(penuh, as_attachment=True, download_name=filename,
                     mimetype='application/octet-stream')


@database_bp.route('/backup/<path:filename>', methods=['DELETE'])
def delete_backup(filename):
    try:
        hapus_backup(filename)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400
    log_activity('DB_BACKUP_DELETE', get_current_user_id(),
                 f"Menghapus backup {filename}", 'Database', None)
    return jsonify({'deleted': filename})


@database_bp.route('/restore', methods=['POST'])
def restore():
    """
    Pulihkan dari berkas .bak yang diunggah, atau dari salah satu backup yang
    sudah ada di server ({"filename": "..."}).

    Ini menimpa SELURUH basis data, dan wajib disetujui Superadmin dengan sandi
    yang diketik saat itu juga. Keduanya ditegakkan di sini, bukan hanya di
    tampilan: siapa pun yang memegang token Admin/Owner bisa memanggil endpoint
    ini langsung.
    """
    request.max_content_length = MAKS_UNGGAH

    berkas = request.files.get('file')
    diunggah = berkas is not None and berkas.filename

    if diunggah:
        data = request.form
        nama_asli = berkas.filename
    else:
        data = request.get_json(silent=True) or {}
        nama_asli = data.get('filename') or ''

    if (data.get('confirm') or '').strip().upper() != 'PULIHKAN':
        return jsonify({
            'error': 'Restore menimpa seluruh data. Kirim confirm="PULIHKAN" untuk melanjutkan.'
        }), 400

    # Diperiksa SEBELUM berkas unggahan disimpan: konfirmasi yang gagal tidak
    # boleh sempat menulis apa pun ke folder cadangan.
    nama_penyetuju, galat = _izin_superadmin(data)
    if galat:
        return galat

    sementara = None
    try:
        if diunggah:
            # Ditulis ke folder backup, bukan ke temp milik Flask: SQL Server yang
            # membaca berkas ini, dan folder temp proses Flask belum tentu
            # terjangkau layanan SQL Server.
            if not nama_asli.lower().endswith('.bak'):
                return jsonify({'error': 'Hanya berkas .bak yang bisa dipulihkan.'}), 400
            # Nama berkas dari pengguna tidak dipakai sama sekali untuk menamai
            # berkas di disk -- hanya untuk catatan log. Nama aslinya bisa berisi
            # spasi, huruf non-ASCII, atau '..'; tidak ada gunanya diselamatkan.
            sementara = path_backup(f'upload-{os.getpid()}.bak', harus_ada=False)
            berkas.save(sementara)
            sumber = sementara
        else:
            sumber = path_backup(nama_asli)

        hasil = pulihkan_backup(sumber)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400
    finally:
        if sementara and os.path.isfile(sementara):
            try:
                os.remove(sementara)
            except OSError:
                pass

    # Dicatat setelah restore, jadi barisnya masuk ke basis data yang BARU --
    # justru itu yang diinginkan: jejaknya ikut hidup bersama data hasil restore.
    # Dua nama dicatat sekaligus: yang menjalankan dan yang menyetujui. Kalau
    # hanya salah satu, jejaknya tidak bisa menjawab siapa yang memutuskan.
    log_activity('DB_RESTORE', get_current_user_id(),
                 f"Memulihkan basis data dari {nama_asli or 'unggahan'}; "
                 f"disetujui Superadmin {nama_penyetuju}", 'Database', None)
    return jsonify(hasil)
