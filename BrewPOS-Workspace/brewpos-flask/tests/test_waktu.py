"""Waktu yang dikirim ke klien harus ber-zona, kalau tidak struk salah 7 jam."""
from datetime import datetime, timedelta, timezone

from app.waktu import iso_utc
from app.models.transaction import Transaction


def test_iso_utc_menandai_zona_pada_waktu_naif():
    teks = iso_utc(datetime(2026, 8, 20, 3, 15, 0))
    assert teks.endswith('+00:00')
    # Browser harus membacanya sebagai 03:15 UTC, bukan 03:15 lokal.
    assert datetime.fromisoformat(teks) == datetime(2026, 8, 20, 3, 15, tzinfo=timezone.utc)


def test_iso_utc_none_tetap_none():
    assert iso_utc(None) is None


def test_transaksi_dini_hari_terbaca_di_hari_yang_benar_di_wib():
    # 19:30 WIB 20 Agustus = 12:30 UTC 20 Agustus.
    tx = Transaction(totalAmount=1, customerId=1, transactionCode='TR20260820000001',
                     createdAt=datetime(2026, 8, 20, 12, 30))
    teks = tx.to_dict(include_items=False, include_customer=False)['createdAt']
    wib = datetime.fromisoformat(teks).astimezone(timezone(timedelta(hours=7)))
    assert (wib.day, wib.hour) == (20, 19)
