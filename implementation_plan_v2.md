# Rencana Implementasi: Fitur & Hak Akses Role "HEADBAR" di Mobile

Berdasarkan struktur sistem kedai kopi pada umumnya dan *schema* database yang Anda miliki (dimana role terdiri dari `ADMIN`, `HEADBAR`, dan `CASHIER`), berikut adalah **Review & Rekomendasi** mengenai apa saja yang harus ada dan boleh dikelola oleh seorang **Head Barista (Headbar)** di aplikasi mobile.

## 1. Hak Akses (Yang Boleh Dikelola HEADBAR)

Seorang *Head Barista* bertanggung jawab atas operasional bar, ketersediaan bahan, dan kelancaran pesanan.
* **Manajemen Stok (Inventory)**: **Akses Penuh**. Headbar wajib bisa melihat, menambah (Stock In), dan mengurangi (Stock Out) bahan baku. Mereka adalah penanggung jawab utama fitur di `InventoryScreen`.
* **Ketersediaan Menu (Menu Availability)**: Headbar harus bisa mematikan/menandai menu sebagai "Habis (Sold Out)" langsung dari aplikasi mobile agar kasir tidak bisa menjual menu yang bahannya sudah kosong.
* **Laporan Operasional (Report)**: **Akses Terbatas**. Boleh melihat halaman `ReportScreen` untuk mengetahui "Menu Terlaris" hari ini. Ini krusial agar mereka bisa meramalkan (forecasting) bahan baku mana yang harus segera dibelanjakan.
* **Riwayat & Kasir (POS & History)**: **Akses Penuh**. Seringkali Headbar juga turun tangan melayani pelanggan atau mengecek riwayat transaksi jika ada komplain pesanan.

## 2. Batasan (Yang TIDAK Boleh Dikelola HEADBAR)

* **Pengaturan Sistem Utama (Settings)**: Headbar tidak boleh mengubah Nama Toko, Logo, Warna Tema, atau Pajak. Pengaturan ini ditarik secara dinamis dari Web dan murni hak `ADMIN`.
* **Keuangan & Void**: Tidak boleh membatalkan (Void) transaksi yang sudah terekam tanpa persetujuan Admin/Owner.
* **Manajemen Pengguna (User Management)**: Tidak bisa membuat akun kasir baru atau melihat kata sandi karyawan lain.

---

## Open Questions & Persetujuan

> [!IMPORTANT]  
> **Masalah Teknis Saat Ini:** Pada file `login_screen.dart`, saat pengguna login, data `user` dan `role` dari API belum disimpan di memori aplikasi (langsung dibuang dan pindah ke halaman utama).

**Langkah Implementasi yang Saya Usulkan:**
1. **Membuat `AuthProvider`**: Untuk menyimpan data user yang sedang login (termasuk `role`-nya) agar aplikasi tahu siapa yang sedang memakai perangkat.
2. **Menyesuaikan Tampilan Navigasi (`MainScreen`)**:
   - Jika yang login **CASHIER**: Tab "Laporan" mungkin disembunyikan. Tab "Stok" hanya bisa *melihat* saja, tidak bisa mengubah.
   - Jika yang login **HEADBAR**: Semua Tab terbuka (POS, Riwayat, Laporan operasional, dan edit Stok).
3. **Mengunci Fitur Tertentu**: Memberikan peringatan "Akses Ditolak" jika role yang salah mencoba mengakses fitur terlarang.

Apakah Anda setuju dengan pembagian hak akses ini dan ingin saya mulai mengerjakan implementasinya (mulai dari menyimpan `role` saat Login hingga mengatur kunci navigasi)? Atau ada fitur khusus lain yang ingin Anda berikan ke role HEADBAR?
