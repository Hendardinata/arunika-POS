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
    Buang tiket yang lewat waktu.

    Berkasnya tidak ikut disentuh: semua cadangan tinggal di riwayat, dan tiket
    hanya izin mengunduh salinannya. Tiket yang tidak pernah ditukar berarti
    unduhannya batal -- bukan berarti cadangannya harus hilang.
    """
    for token in [t for t, d in _tiket.items() if d['kedaluwarsa'] < sekarang]:
        _tiket.pop(token, None)


def terbitkan(path, nama_unduh, user_id=None):
    """Tiket baru untuk satu berkas. Mengembalikan tokennya."""
    sekarang = time.time()
    token = secrets.token_urlsafe(32)
    with _lock:
        _buang_kedaluwarsa(sekarang)
        _tiket[token] = {
            'path': path,
            'nama': nama_unduh,
            'userId': user_id,
            'kedaluwarsa': sekarang + UMUR_DETIK,
        }
    return token


def tukar(token):
    """
    Tukar tiket dengan (path, nama). SEKALI PAKAI: tiket langsung dicabut,
    berhasil atau tidak berkasnya nanti terbaca.

    Mengembalikan None bila tiket tidak dikenal atau sudah lewat waktu.
    """
    sekarang = time.time()
    with _lock:
        _buang_kedaluwarsa(sekarang)
        data = _tiket.pop(token or '', None)
    if not data:
        return None
    return data['path'], data['nama']


def reset_all():
    """Untuk test."""
    with _lock:
        _tiket.clear()
