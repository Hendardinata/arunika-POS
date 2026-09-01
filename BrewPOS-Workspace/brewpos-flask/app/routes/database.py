"""
Manajemen basis data: unduh backup dan pulihkan dari backup.

Semuanya dikunci SUPERADMIN. Berkas .bak berisi SELURUH isi basis data --
termasuk hash sandi setiap akun -- jadi mengunduhnya sama beratnya dengan
memulihkannya, dan tidak cukup dijaga level Admin.
"""

import os

from flask import Blueprint, jsonify, request, send_file

from app.middleware.auth import (ROLE_LEVELS, get_current_user_id,
                                 has_role_level)
from app.services.db_backup import (DbBackupError, buat_backup, daftar_backup,
                                    hapus_backup, path_backup, pulihkan_backup)
from app.services.system_logger import log_activity

database_bp = Blueprint('database', __name__, url_prefix='/api/database')

# Berkas .bak jauh melampaui MAX_CONTENT_LENGTH global (16 MB, ukuran untuk foto
# nota). Batasnya dinaikkan per-request saja, supaya jalur unggah lain tetap
# terjaga di angka kecilnya.
MAKS_UNGGAH = 4 * 1024 * 1024 * 1024   # 4 GB


def _tolak_bukan_superadmin():
    if not has_role_level(ROLE_LEVELS['SUPERADMIN']):
        return jsonify({'error': 'Manajemen basis data memerlukan otorisasi Superadmin'}), 403
    return None


@database_bp.before_request
def _gerbang():
    return _tolak_bukan_superadmin()


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

    Ini menimpa SELURUH basis data. Konfirmasinya dituntut di sini, bukan hanya
    di tampilan: siapa pun yang memegang token Superadmin bisa memanggil endpoint
    ini langsung.
    """
    request.max_content_length = MAKS_UNGGAH

    berkas = request.files.get('file')
    diunggah = berkas is not None and berkas.filename

    if diunggah:
        konfirmasi = (request.form.get('confirm') or '').strip()
        nama_asli = berkas.filename
    else:
        data = request.get_json(silent=True) or {}
        konfirmasi = (data.get('confirm') or '').strip()
        nama_asli = data.get('filename') or ''

    if konfirmasi.upper() != 'PULIHKAN':
        return jsonify({
            'error': 'Restore menimpa seluruh data. Kirim confirm="PULIHKAN" untuk melanjutkan.'
        }), 400

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
    log_activity('DB_RESTORE', get_current_user_id(),
                 f"Memulihkan basis data dari {nama_asli or 'unggahan'}", 'Database', None)
    return jsonify(hasil)
