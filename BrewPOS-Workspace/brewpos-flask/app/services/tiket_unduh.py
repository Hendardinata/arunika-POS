"""
Tiket unduhan sekali pakai.

Kenapa perlu. Unduhan cadangan sebelumnya diambil dengan fetch + blob + <a
download>. Itu bekerja di browser desktop, tapi TIDAK di WebView Android: di
sana DownloadListener -- satu-satunya jalan menyerahkan berkas ke pengunduh
sistem -- tidak pernah menyala untuk URL `blob:`. Aplikasi kasir jadi diam saja
saat tombolnya ditekan.

Menyerahkan 12 MB base64 lewat jembatan JavaScript bukan jawaban. Yang benar
adalah membuat unduhannya jadi permintaan GET biasa, karena setiap platform
sudah tahu cara menangani itu: DownloadManager di Android, pengelola unduhan
Safari di iOS, dan unduhan bawaan di browser desktop.

Masalahnya, navigasi tidak bisa membawa header Authorization. Maka tiket ini:
tautan sekali pakai berumur pendek yang menggantikan token untuk satu unduhan
saja.

Disimpan di memori proses, sama seperti login_guard, dan dengan alasan yang
sama: server ini satu proses tunggal, dan tiket yang hilang saat restart justru
aman -- yang batal cuma satu unduhan. Kalau nanti jalan multi-worker, pindahkan
ke Redis.
"""
import os
import secrets
import threading
import time

# Cukup untuk berpindah dari respons POST ke navigasi unduhan, tidak cukup untuk
# tautan yang tercecer di riwayat browser jadi berguna nanti.
UMUR_DETIK = 120

_tiket = {}
_lock = threading.Lock()


def _buang_kedaluwarsa(sekarang):
    """
    Hapus tiket lewat waktu, beserta berkasnya bila itu salinan sekali pakai.

    Ini yang menutup kasus "tombol ditekan, unduhan tidak pernah dimulai":
    tanpa langkah ini berkas 12 MB berisi seluruh basis data akan menunggu di
    server sampai penyapu satu jam lewat.
    """
    for token in [t for t, d in _tiket.items() if d['kedaluwarsa'] < sekarang]:
        data = _tiket.pop(token, None)
        if data and data.get('hapusSetelah'):
            _hapus_berkas(data['path'])


def _hapus_berkas(path):
    try:
        os.remove(path)
    except OSError:
        pass


def terbitkan(path, nama_unduh, user_id=None, hapus_setelah=False):
    """
    Tiket baru untuk satu berkas. Mengembalikan tokennya.

    hapus_setelah=True untuk salinan sekali pakai (jalur "buat & unduh"):
    berkasnya dihapus begitu terkirim, dan juga bila tiketnya keburu lewat waktu
    tanpa pernah ditukar. Riwayat cadangan memakai False -- berkasnya memang
    harus tetap ada.
    """
    sekarang = time.time()
    token = secrets.token_urlsafe(32)
    with _lock:
        _buang_kedaluwarsa(sekarang)
        _tiket[token] = {
            'path': path,
            'nama': nama_unduh,
            'userId': user_id,
            'hapusSetelah': hapus_setelah,
            'kedaluwarsa': sekarang + UMUR_DETIK,
        }
    return token


def tukar(token):
    """
    Tukar tiket dengan (path, nama, hapus_setelah). SEKALI PAKAI: tiket langsung
    dicabut, berhasil atau tidak berkasnya nanti terbaca.

    Mengembalikan None bila tiket tidak dikenal atau sudah lewat waktu.
    """
    sekarang = time.time()
    with _lock:
        _buang_kedaluwarsa(sekarang)
        data = _tiket.pop(token or '', None)
    if not data:
        return None
    return data['path'], data['nama'], data['hapusSetelah']


def reset_all():
    """Untuk test."""
    with _lock:
        _tiket.clear()
