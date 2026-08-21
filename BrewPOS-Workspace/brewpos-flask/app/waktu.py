"""
Satu tempat untuk mengubah waktu naif UTC jadi teks yang dikirim ke klien.

Seluruh aplikasi menyimpan datetime naif UTC (lihat parse_waktu di
routes/checkout.py). `datetime.isoformat()` pada nilai naif menghasilkan
"2026-08-20T03:15:00" -- tanpa zona. Dan `new Date("2026-08-20T03:15:00")` di
browser membacanya sebagai waktu LOKAL, bukan UTC. Akibatnya struk dan seluruh
tampilan tanggal meleset 7 jam di WIB, dan transaksi dini hari tercetak dengan
tanggal kemarin.

Dengan akhiran "Z" browser tahu itu UTC dan menampilkannya dalam waktu
perangkat: server tetap menyimpan UTC, kasir tetap membaca jam dinding kafe.
"""
from datetime import timezone


def iso_utc(nilai):
    """datetime naif UTC -> teks ISO ber-zona ('...+00:00'). None -> None."""
    if nilai is None:
        return None
    if nilai.tzinfo is None:
        nilai = nilai.replace(tzinfo=timezone.utc)
    return nilai.isoformat()
