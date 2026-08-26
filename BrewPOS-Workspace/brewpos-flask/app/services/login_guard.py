"""
Rem percobaan login. Tanpa ini /api/auth/login menerima tebakan password
tanpa batas -- tidak masalah selama server hanya dijangkau tailnet, tapi
begitu Tailscale Funnel dinyalakan halaman login menghadap internet dan bot
pemindai akan menemukannya dalam hitungan jam.

Disimpan di memori proses, bukan tabel: server ini satu proses tunggal, dan
kunci yang hilang saat restart justru aman -- restart mengosongkan rem, tidak
mengunci kasir. Kalau nanti jalan multi-worker, pindahkan ke Redis.
"""
import time
import threading

# 8 kegagalan dalam 15 menit -> tertahan sampai jendela itu lewat. Cukup longgar
# untuk kasir yang salah ketik beberapa kali, cukup ketat untuk mematikan
# tebakan otomatis.
WINDOW_SECONDS = 15 * 60
MAX_FAILURES = 8

_failures = {}
_lock = threading.Lock()


def client_ip():
    """
    IP pemanggil. Di belakang `tailscale serve`/Funnel semua request datang dari
    127.0.0.1, jadi remote_addr sendirian akan menggabung seluruh internet jadi
    satu kunci -- satu penyerang bisa mengunci semua orang. X-Forwarded-For yang
    dipasang Tailscale dibaca lebih dulu.
    """
    from flask import request
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _prune(hits, now):
    return [t for t in hits if now - t < WINDOW_SECONDS]


def _keys(username):
    return (f"user:{(username or '').strip().lower()}", f"ip:{client_ip()}")


def seconds_until_unlocked(username):
    """Sisa detik penahanan, 0 kalau boleh mencoba."""
    now = time.time()
    longest = 0
    with _lock:
        for key in _keys(username):
            hits = _prune(_failures.get(key, []), now)
            _failures[key] = hits
            if len(hits) >= MAX_FAILURES:
                remaining = int(WINDOW_SECONDS - (now - hits[0])) + 1
                longest = max(longest, remaining)
    return longest


def record_failure(username):
    now = time.time()
    with _lock:
        for key in _keys(username):
            _failures[key] = _prune(_failures.get(key, []), now) + [now]


def clear(username):
    """Login berhasil menghapus rem untuk username dan IP tersebut."""
    with _lock:
        for key in _keys(username):
            _failures.pop(key, None)


def reset_all():
    """Hanya untuk tes."""
    with _lock:
        _failures.clear()
