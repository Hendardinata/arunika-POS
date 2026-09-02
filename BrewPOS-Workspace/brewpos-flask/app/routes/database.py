"""
Manajemen basis data: unduh backup dan pulihkan dari backup.

Izinnya dibagi menurut satu garis: siapa yang boleh menyentuh PENYIMPANAN
cadangan, dan siapa yang cuma boleh mengambil salinan untuk dirinya sendiri.

- Admin/Owner: satu kemampuan saja -- "buat & unduh". Berkasnya dibuat, dikirim
  ke pengunduh, lalu dihapus dari server. Tidak masuk riwayat, tidak bisa
  diambil lagi nanti.
- Superadmin: pemilik penuh riwayat cadangan -- melihat daftar, menyimpan,
  mengunduh ulang, menghapus.

Pemisahan itu yang menutup celahnya. Kalau Owner boleh membaca daftar cadangan,
ia juga bisa mengunduh cadangan yang dibuat Superadmin kapan saja -- dan tiap
berkas .bak berisi SELURUH isi basis data, termasuk hash sandi setiap akun.
Dengan "buat & unduh", Owner hanya pernah memegang salinan yang ia buat sendiri
saat itu juga, dan server tidak menyimpan apa pun untuknya.

Memulihkan dipecah jadi dua tindakan oleh dua orang: Admin/Owner MENGAJUKAN,
Superadmin MEMUTUSKAN dari halamannya sendiri. Restore menimpa seluruh isi toko
dan tidak bisa dibatalkan, jadi keputusannya tidak boleh jatuh pada satu orang
di satu klik.

Sengaja BUKAN dengan meminta sandi Superadmin diketik di layar pemohon: itu
memaksa sandi berpindah tangan, dan begitu berpindah ia tidak bisa ditarik lagi.
Di sini masing-masing bertindak sambil masuk sebagai dirinya sendiri, dan
jejaknya menyebut dua nama yang berbeda.
"""

import os
import secrets
from datetime import datetime, timedelta
from io import BytesIO

from flask import Blueprint, jsonify, request, send_file

from app.extensions import db
from app.middleware.auth import (ROLE_LEVELS, get_current_user_id,
                                 has_role_level)
from app.models.restore_request import UMUR_JAM, RestoreRequest
from app.services import tiket_unduh
from app.services.db_backup import (AWALAN_TERSEMBUNYI, DbBackupError,
                                    buat_backup, daftar_backup, hapus_backup,
                                    path_backup, pulihkan_backup,
                                    sapu_berkas_sementara)
from app.services.system_logger import log_activity

database_bp = Blueprint('database', __name__, url_prefix='/api/database')

# Rute unduhan berdiri di luar /api/ dengan sengaja. Middleware auth menjaga
# seluruh /api/ dengan header Authorization, sementara unduhan ini dijangkau
# lewat NAVIGASI -- dan navigasi tidak bisa membawa header. Yang mengesahkannya
# tiket sekali pakai di dalam URL, bukan token. Menaruhnya di luar /api/ berarti
# middleware tidak perlu dilubangi sama sekali.
unduh_bp = Blueprint('unduh', __name__)

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


def _wajib_superadmin():
    """Gerbang untuk endpoint yang menyentuh penyimpanan cadangan."""
    if not has_role_level(ROLE_LEVELS['SUPERADMIN']):
        return jsonify({
            'error': 'Riwayat cadangan hanya untuk Superadmin. '
                     'Pakai "Buat & Unduh Cadangan" untuk mengambil salinan sendiri.'
        }), 403
    return None


def _permintaan_menggantung():
    """Permintaan restore yang masih menunggu keputusan, atau None."""
    _buang_permintaan_kedaluwarsa()
    return (RestoreRequest.query
            .filter_by(status='PENDING')
            .order_by(RestoreRequest.createdAt.desc())
            .first())


def _buang_permintaan_kedaluwarsa():
    """
    Tutup permintaan yang menganggur lewat batas, dan buang berkas unggahannya.

    Berkas itu berisi seluruh basis data. Tanpa langkah ini, permintaan yang
    dilupakan meninggalkannya di server tanpa batas waktu.
    """
    batas = datetime.utcnow() - timedelta(hours=UMUR_JAM)
    basi = RestoreRequest.query.filter(
        RestoreRequest.status == 'PENDING',
        RestoreRequest.createdAt < batas).all()
    if not basi:
        return
    for p in basi:
        p.status = 'CANCELLED'
        p.decisionNote = f'Kedaluwarsa otomatis setelah {UMUR_JAM} jam tanpa keputusan'
        p.decidedAt = datetime.utcnow()
        _buang_berkas_unggahan(p)
    db.session.commit()


def _buang_berkas_unggahan(permintaan):
    """Hapus berkas unggahan milik satu permintaan. Berkas riwayat tidak disentuh."""
    if permintaan.sourceType != 'UPLOAD':
        return
    try:
        os.remove(path_backup(permintaan.storedName, harus_ada=False))
    except (OSError, DbBackupError):
        pass


@database_bp.route('/backups', methods=['GET'])
def list_backups():
    galat = _wajib_superadmin()
    if galat:
        return galat
    try:
        return jsonify(daftar_backup())
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400


@database_bp.route('/backup-latest', methods=['GET'])
def cadangan_terakhir():
    """
    Satu baris: cadangan terbaru yang tersimpan di server. Admin/Owner ke atas.

    Riwayat lengkapnya tetap tertutup -- yang dijawab di sini cuma "kapan toko
    ini terakhir dicadangkan", dan itu pertanyaan yang berhak diketahui
    pemiliknya. Hanya keterangannya: nama, ukuran, tanggal. Tidak ada tautan
    unduhan, jadi Owner tetap tidak bisa mengambil cadangan buatan Superadmin.

    Berbeda dari "buat & unduh" milik Owner sendiri, yang memang tidak disimpan
    dan karena itu tidak pernah muncul di sini.
    """
    try:
        data = daftar_backup()
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400
    daftar = data['backups']
    return jsonify({
        'database': data['database'],
        'latest': daftar[0] if daftar else None,
    })


@database_bp.route('/backup', methods=['POST'])
def create_backup():
    """Buat cadangan dan SIMPAN di riwayat server."""
    galat = _wajib_superadmin()
    if galat:
        return galat
    try:
        info = buat_backup()
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400
    log_activity('DB_BACKUP', get_current_user_id(),
                 f"Membuat backup {info['filename']}", 'Database', None)
    return jsonify(info), 201


@database_bp.route('/backup/<path:filename>', methods=['GET'])
def download_backup(filename):
    galat = _wajib_superadmin()
    if galat:
        return galat
    if (filename or '').startswith(AWALAN_TERSEMBUNYI):
        return jsonify({'error': 'Berkas kerja sementara tidak bisa diunduh.'}), 404
    try:
        penuh = path_backup(filename)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 404
    log_activity('DB_BACKUP_DOWNLOAD', get_current_user_id(),
                 f"Mengunduh backup {filename}", 'Database', None)
    return send_file(penuh, as_attachment=True, download_name=filename,
                     mimetype='application/octet-stream')


@database_bp.route('/backup/<path:filename>/tiket', methods=['POST'])
def tiket_unduh_riwayat(filename):
    """
    Tiket unduhan untuk satu berkas di riwayat (Superadmin).

    Berkasnya TIDAK dihapus setelah diunduh -- ini riwayat, bukan salinan sekali
    pakai. Yang sekali pakai hanya tiketnya.
    """
    galat = _wajib_superadmin()
    if galat:
        return galat
    if (filename or '').startswith(AWALAN_TERSEMBUNYI):
        return jsonify({'error': 'Berkas kerja sementara tidak bisa diunduh.'}), 404
    try:
        penuh = path_backup(filename)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 404

    log_activity('DB_BACKUP_DOWNLOAD', get_current_user_id(),
                 f"Mengunduh backup {filename}", 'Database', None)
    token = tiket_unduh.terbitkan(penuh, filename, get_current_user_id(), hapus_setelah=False)
    return jsonify({'url': f'/unduh-cadangan/{token}', 'filename': filename}), 201


@database_bp.route('/backup/<path:filename>', methods=['DELETE'])
def delete_backup(filename):
    galat = _wajib_superadmin()
    if galat:
        return galat
    try:
        hapus_backup(filename)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400
    log_activity('DB_BACKUP_DELETE', get_current_user_id(),
                 f"Menghapus backup {filename}", 'Database', None)
    return jsonify({'deleted': filename})


@database_bp.route('/backup-download', methods=['POST'])
def backup_and_download():
    """
    Buat cadangan, kirim ke pengunduh, lalu hapus dari server.

    Ini satu-satunya jalur cadangan untuk Admin/Owner. Berkasnya tidak masuk
    riwayat dan tidak bisa diambil lagi nanti -- server tidak menyimpan apa pun
    untuk peran ini.

    Alamatnya sengaja /backup-download, bukan /backup/download: rute tetangganya
    memakai <path:filename> yang rakus, dan alamat terpisah menghilangkan
    pertanyaan mana yang cocok lebih dulu.
    """
    # Sisa berkas dari permintaan yang mati di tengah pengiriman dibersihkan di
    # sini. Isinya seluruh basis data; tidak boleh menumpuk diam-diam.
    sapu_berkas_sementara()

    try:
        info = buat_backup(sementara=True)
        penuh = path_backup(info['filename'])
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400

    # Nama yang dilihat pengunduh tidak membawa awalan kerja "unduh-".
    nama_unduh = info['filename'][len('unduh-'):]

    log_activity('DB_BACKUP_DOWNLOAD', get_current_user_id(),
                 f"Membuat & mengunduh cadangan {nama_unduh} (tidak disimpan di server)",
                 'Database', None)

    token = tiket_unduh.terbitkan(penuh, nama_unduh, get_current_user_id(),
                                  hapus_setelah=True)
    return jsonify({'url': f'/unduh-cadangan/{token}', 'filename': nama_unduh}), 201


@unduh_bp.route('/unduh-cadangan/<token>', methods=['GET'])
def ambil_cadangan(token):
    """
    Serahkan berkas cadangan sekali, lalu lupakan.

    Sengaja GET biasa tanpa header: inilah bentuk yang dimengerti pengunduh
    bawaan setiap platform -- DownloadManager di Android, Safari di iOS, dan
    browser desktop. Tiket di URL yang menggantikan token, dan tiketnya dicabut
    begitu ditukar.
    """
    hasil = tiket_unduh.tukar(token)
    if not hasil:
        return jsonify({
            'error': 'Tautan unduhan sudah dipakai atau kedaluwarsa. Buat cadangan lagi.'
        }), 404

    penuh, nama_unduh, hapus_setelah = hasil

    # Dibaca ke memori lalu berkasnya DIHAPUS SEKARANG, sebelum respons dikirim.
    #
    # Percobaan sebelumnya memakai send_file + call_on_close supaya berkasnya
    # mengalir tanpa singgah di memori. Hasilnya: berkasnya TERTINGGAL -- terbukti
    # tiga .bak 12 MB menumpuk setelah tiga permintaan. Untuk berkas berisi
    # seluruh basis data, "biasanya terhapus" bukan jaminan yang cukup. Menghapus
    # lebih dulu membuat kegagalan itu mustahil.
    #
    # ponytail: seluruh .bak masuk memori (12 MB untuk basis data ini). Kalau
    # nanti tumbuh ke ratusan MB, kembali ke aliran -- tapi dengan penghapus yang
    # benar-benar diuji, bukan diasumsikan.
    try:
        with open(penuh, 'rb') as f:
            isi = f.read()
    except OSError as e:
        return jsonify({'error': f'Berkas cadangan tidak bisa dibaca: {e}'}), 404
    finally:
        if hapus_setelah:
            try:
                os.remove(penuh)
            except OSError:
                pass   # terkunci di Windows; disapu permintaan berikutnya

    return send_file(BytesIO(isi), as_attachment=True, download_name=nama_unduh,
                     mimetype='application/octet-stream')


# ==============================================================================
# Permintaan & persetujuan restore
# ==============================================================================

@database_bp.route('/restore-request', methods=['GET'])
def daftar_permintaan():
    """
    Permintaan yang perlu dilihat pemanggil.

    Superadmin melihat semuanya -- inilah kotak masuk persetujuannya. Admin/Owner
    melihat miliknya sendiri, supaya tahu permintaannya sudah diputus atau belum.
    """
    _buang_permintaan_kedaluwarsa()
    q = RestoreRequest.query
    if not has_role_level(ROLE_LEVELS['SUPERADMIN']):
        q = q.filter_by(requestedBy=get_current_user_id())
    baris = q.order_by(RestoreRequest.createdAt.desc()).limit(20).all()
    return jsonify({
        'canApprove': has_role_level(ROLE_LEVELS['SUPERADMIN']),
        'requests': [b.to_dict() for b in baris],
    })


@database_bp.route('/restore-request', methods=['POST'])
def ajukan_permintaan():
    """
    Ajukan pemulihan, dari berkas riwayat atau dari berkas .bak yang diunggah.

    Satu permintaan menggantung pada satu waktu. Antrean permintaan restore tidak
    masuk akal -- yang kedua akan memulihkan di atas hasil yang pertama -- dan
    tiap permintaan unggahan menahan satu berkas seukuran seluruh basis data.
    """
    request.max_content_length = MAKS_UNGGAH

    berkas = request.files.get('file')
    diunggah = berkas is not None and berkas.filename
    data = request.form if diunggah else (request.get_json(silent=True) or {})

    alasan = (data.get('reason') or '').strip()
    if len(alasan) < 10:
        return jsonify({
            'error': 'Tulis alasan pemulihan (minimal 10 karakter). '
                     'Superadmin memutuskan berdasarkan alasan ini.'
        }), 400

    if _permintaan_menggantung():
        return jsonify({
            'error': 'Masih ada permintaan pemulihan yang menunggu keputusan. '
                     'Batalkan dulu sebelum mengajukan yang baru.'
        }), 409

    if diunggah:
        if not berkas.filename.lower().endswith('.bak'):
            return jsonify({'error': 'Hanya berkas .bak yang bisa dipulihkan.'}), 400
        # Menunggu di folder cadangan dengan awalan yang menyembunyikannya dari
        # riwayat. Nama dari pengguna tidak dipakai untuk menamai berkas di disk.
        disimpan = f'pending-{secrets.token_hex(8)}.bak'
        try:
            berkas.save(path_backup(disimpan, harus_ada=False))
        except DbBackupError as e:
            return jsonify({'error': str(e)}), 400
        nama_tampil = os.path.basename(berkas.filename)
        jenis = 'UPLOAD'
    else:
        nama_tampil = disimpan = data.get('filename') or ''
        try:
            path_backup(disimpan)          # memastikan berkasnya benar-benar ada
        except DbBackupError as e:
            return jsonify({'error': str(e)}), 400
        jenis = 'HISTORY'

    permintaan = RestoreRequest(
        requestedBy=get_current_user_id(), sourceType=jenis,
        filename=nama_tampil, storedName=disimpan, reason=alasan)
    db.session.add(permintaan)
    db.session.commit()

    log_activity('DB_RESTORE_REQUEST', get_current_user_id(),
                 f'Mengajukan pemulihan dari {nama_tampil}; alasan: {alasan}',
                 'RestoreRequest', permintaan.id)
    return jsonify(permintaan.to_dict()), 201


@database_bp.route('/restore-request/<int:permintaan_id>', methods=['DELETE'])
def batalkan_permintaan(permintaan_id):
    """Pemohon menarik permintaannya sendiri; Superadmin juga boleh membersihkan."""
    permintaan = RestoreRequest.query.get(permintaan_id)
    if not permintaan or permintaan.status != 'PENDING':
        return jsonify({'error': 'Permintaan tidak ditemukan atau sudah diputus.'}), 404

    milik_sendiri = permintaan.requestedBy == get_current_user_id()
    if not milik_sendiri and not has_role_level(ROLE_LEVELS['SUPERADMIN']):
        return jsonify({'error': 'Hanya pemohon atau Superadmin yang bisa membatalkan.'}), 403

    permintaan.status = 'CANCELLED'
    permintaan.decidedBy = get_current_user_id()
    permintaan.decidedAt = datetime.utcnow()
    _buang_berkas_unggahan(permintaan)
    db.session.commit()
    log_activity('DB_RESTORE_CANCEL', get_current_user_id(),
                 f'Membatalkan permintaan pemulihan #{permintaan_id}',
                 'RestoreRequest', permintaan_id)
    return jsonify(permintaan.to_dict())


@database_bp.route('/restore-request/<int:permintaan_id>/reject', methods=['POST'])
def tolak_permintaan(permintaan_id):
    galat = _wajib_superadmin()
    if galat:
        return galat

    permintaan = RestoreRequest.query.get(permintaan_id)
    if not permintaan or permintaan.status != 'PENDING':
        return jsonify({'error': 'Permintaan tidak ditemukan atau sudah diputus.'}), 404

    catatan = ((request.get_json(silent=True) or {}).get('note') or '').strip()
    permintaan.status = 'REJECTED'
    permintaan.decidedBy = get_current_user_id()
    permintaan.decidedAt = datetime.utcnow()
    permintaan.decisionNote = catatan or 'Ditolak tanpa catatan'
    _buang_berkas_unggahan(permintaan)
    db.session.commit()
    log_activity('DB_RESTORE_REJECT', get_current_user_id(),
                 f'Menolak permintaan pemulihan #{permintaan_id}: {permintaan.decisionNote}',
                 'RestoreRequest', permintaan_id)
    return jsonify(permintaan.to_dict())


@database_bp.route('/restore-request/<int:permintaan_id>/approve', methods=['POST'])
def setujui_permintaan(permintaan_id):
    """
    Setujui SEKALIGUS jalankan pemulihannya.

    Sengaja satu tindakan, bukan "disetujui" lalu "dijalankan" belakangan:
    permintaan yang sudah disetujui tapi belum dijalankan adalah izin menghapus
    isi toko yang menganggur -- dan siapa pun yang menemukannya nanti tinggal
    menekan tombol.
    """
    galat = _wajib_superadmin()
    if galat:
        return galat

    permintaan = RestoreRequest.query.get(permintaan_id)
    if not permintaan or permintaan.status != 'PENDING':
        return jsonify({'error': 'Permintaan tidak ditemukan atau sudah diputus.'}), 404

    # Konfirmasi ketikan tetap ada. Ini bukan sandi, melainkan pengaman terakhir
    # supaya tombol Setujui tidak bisa tertekan tanpa sengaja.
    if ((request.get_json(silent=True) or {}).get('confirm') or '').strip().upper() != 'PULIHKAN':
        return jsonify({
            'error': 'Restore menimpa seluruh data. Kirim confirm="PULIHKAN" untuk melanjutkan.'
        }), 400

    nama_tampil = permintaan.filename
    pemohon = permintaan.pemohon.username if permintaan.pemohon else 'tidak diketahui'

    try:
        sumber = path_backup(permintaan.storedName)
    except DbBackupError as e:
        return jsonify({'error': str(e)}), 400

    # Keputusannya dicatat SEBELUM restore jalan. Barisnya sendiri memang tidak
    # akan selamat -- restore menimpa seluruh basis data, termasuk tabel ini --
    # tapi urutan ini yang benar kalau restore gagal di tengah: statusnya sudah
    # menyebut siapa yang memutuskan, bukan tertinggal PENDING selamanya.
    permintaan.status = 'APPROVED'
    permintaan.decidedBy = get_current_user_id()
    permintaan.decidedAt = datetime.utcnow()
    db.session.commit()

    try:
        hasil = pulihkan_backup(sumber)
    except DbBackupError as e:
        permintaan.status = 'FAILED'
        permintaan.decisionNote = str(e)[:500]
        db.session.commit()
        return jsonify({'error': str(e)}), 400
    finally:
        if permintaan.sourceType == 'UPLOAD':
            _buang_berkas_unggahan(permintaan)

    # Ditulis setelah restore, jadi masuk ke basis data yang BARU. Tabel
    # RestoreRequest ikut tertimpa isi cadangan, jadi baris permintaannya hilang
    # -- catatan inilah satu-satunya jejak yang tersisa, dan ia menyebut dua nama.
    log_activity('DB_RESTORE', get_current_user_id(),
                 f'Memulihkan basis data dari {nama_tampil}; '
                 f'diajukan {pemohon}, disetujui {_nama_pemanggil()}',
                 'Database', None)
    return jsonify({**hasil, 'requestedBy': pemohon})


def _nama_pemanggil():
    from app.middleware.auth import get_current_user
    u = get_current_user()
    return u.username if u else 'tidak diketahui'


@database_bp.route('/restore', methods=['POST'])
def restore():
    """
    Pemulihan langsung oleh Superadmin, tanpa lewat permintaan.

    Superadmin adalah yang menyetujui; memintanya mengajukan permintaan kepada
    dirinya sendiri hanya menambah langkah tanpa menambah pengaman.
    """
    galat = _wajib_superadmin()
    if galat:
        return galat

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

    sementara = None
    try:
        if diunggah:
            if not nama_asli.lower().endswith('.bak'):
                return jsonify({'error': 'Hanya berkas .bak yang bisa dipulihkan.'}), 400
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

    log_activity('DB_RESTORE', get_current_user_id(),
                 f'Memulihkan basis data dari {nama_asli or "unggahan"} (langsung oleh Superadmin)',
                 'Database', None)
    return jsonify(hasil)
