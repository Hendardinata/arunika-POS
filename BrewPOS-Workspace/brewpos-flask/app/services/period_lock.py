"""
Tutup buku: periode yang sudah dikunci tidak bisa diubah lagi.

Praktik standar akuntansi (Odoo Lock Dates, QuickBooks/Xero closing date,
Accurate tutup buku). Prinsipnya: sebelum tutup buku angka boleh dikoreksi,
sesudahnya tidak bisa diganggu gugat -- supaya laporan yang sudah dicetak,
disetor, atau dipakai hitung pajak tidak berubah di belakang.

Ini BUKAN pengganti sesi kas. Sesi kas menjawab "uang di laci cocok tidak"
(harian, per orang yang pegang laci); tutup buku menjawab "laporan periode ini
boleh berubah tidak" (bulanan). Keduanya hidup berdampingan.
"""
from datetime import date, datetime

from app.models.system_settings import get_setting

LOCK_KEY = 'PERIOD_LOCK_DATE'


class PeriodLockedError(Exception):
    """Ditolak karena tanggalnya jatuh di periode yang sudah ditutup."""

    def __init__(self, business_date, lock_date):
        self.business_date = business_date
        self.lock_date = lock_date
        super().__init__(
            f"Buku sudah ditutup sampai {lock_date.isoformat()}. "
            f"Tanggal {business_date.isoformat()} tidak bisa diubah lagi. "
            "Minta Admin membuka kembali periodenya kalau koreksi ini memang perlu."
        )


def as_date(nilai):
    """Terima date, datetime, atau string ISO -> date. None kalau tidak terbaca."""
    if nilai is None:
        return None
    if isinstance(nilai, datetime):
        return nilai.date()
    if isinstance(nilai, date):
        return nilai
    try:
        teks = str(nilai).strip().replace('Z', '')
        return datetime.fromisoformat(teks).date()
    except ValueError:
        try:
            return datetime.strptime(str(nilai)[:10], '%Y-%m-%d').date()
        except ValueError:
            return None


def get_lock_date():
    """Tanggal kunci saat ini, atau None kalau belum pernah tutup buku."""
    return as_date(get_setting(LOCK_KEY))


def is_locked(business_date):
    kunci = get_lock_date()
    tanggal = as_date(business_date)
    if kunci is None or tanggal is None:
        return False
    # Pada tanggal kunci pun sudah terkunci: "ditutup sampai 31 Jan" berarti
    # 31 Jan ikut terkunci, bukan masih bisa diubah.
    return tanggal <= kunci


def assert_period_open(business_date):
    """
    Lempar PeriodLockedError kalau tanggalnya ada di periode tertutup.

    Dipanggil dari setiap jalur tulis yang punya tanggal bisnis. Tanggal yang
    tidak terbaca sengaja dibiarkan lewat -- validasi format itu urusan
    pemanggilnya, dan menolak di sini akan menyamarkan pesan galat yang
    sebenarnya.
    """
    tanggal = as_date(business_date)
    if tanggal is None:
        return
    kunci = get_lock_date()
    if kunci is not None and tanggal <= kunci:
        raise PeriodLockedError(tanggal, kunci)
