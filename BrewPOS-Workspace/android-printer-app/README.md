# ARUNIKA POS — Cangkang Android + Jembatan Printer Bluetooth

Aplikasi tipis: satu WebView yang menampilkan POS dari server, ditambah jembatan
cetak ke printer thermal Bluetooth (Classic/SPP) — misalnya **VSC TM58D Pro 58mm**.

> **Belum pernah dibangun maupun diuji.** Kode ini ditulis lengkap tapi tidak
> tersedia Android SDK maupun printer saat penulisan, jadi build dan uji cetak
> pertama harus Anda jalankan sendiri.

## Kenapa perlu aplikasi

Printer thermal 58mm memakai **Bluetooth Classic (SPP)**, bukan BLE. Web Bluetooth
di browser hanya bisa BLE, dan Firefox tidak mendukungnya sama sekali — itu sebabnya
printer tidak pernah terdeteksi dari browser. Perangkat SPP juga tidak punya koneksi
tingkat sistem: statusnya di Pengaturan Android memang "paired" saja, dan koneksi
dibuka oleh aplikasi tepat saat mencetak. Aplikasi ini melakukan itu.

## Cara kerja

```
Halaman POS  --AndroidPrinter.print(base64)-->  MainActivity
                                                    |
                                        BluetoothSocket (SPP)
                                                    v
                                            Printer thermal
```

Byte ESC/POS disusun di sisi web oleh `app/static/js/escpos.js`, jadi format struk
bisa diubah tanpa membangun ulang APK.

## Build lewat GitHub Actions (tanpa memasang apa pun)

Workflow `.github/workflows/android-apk.yml` membangun APK di server GitHub.

1. Buka repo di GitHub → tab **Actions** → **Build APK Kasir** → **Run workflow**.
2. Isi **posUrl** dengan alamat server POS Anda (mis. `https://pos.contoh.com`).
   Kalau dikosongkan, dipakai nilai bawaan `http://phrolova.echidna-carob.ts.net:3001`.
3. Tunggu build selesai (~3–5 menit), lalu unduh **arunika-pos-apk** di bagian
   *Artifacts* pada halaman run tersebut.
4. Kirim APK-nya ke HP kasir dan pasang (perlu izin "Install unknown apps").

APK yang dihasilkan adalah **debug build** — sudah ditandatangani kunci debug
bawaan sehingga langsung bisa dipasang, tanpa perlu mengurus keystore. Cukup
untuk pemakaian internal; kalau nanti mau lewat Play Store, baru butuh release
build bertanda tangan sendiri.

Setiap push yang menyentuh folder ini juga otomatis memicu build baru.

## Build lokal (alternatif)

Kalau punya Android Studio: **Open** folder ini (sudah lengkap sebagai proyek
Gradle), lalu **Build → Build APK(s)**. Untuk mengganti alamat server tanpa
menyentuh kode:

```
gradle assembleDebug -PposUrl=https://pos.contoh.com
```

## Kalau server masih HTTP

Android memblokir HTTP polos. Daftarkan domain/IP server di
`app/src/main/res/xml/network_security_config.xml`. Begitu server sudah HTTPS,
hapus blok `domain-config` itu beserta baris `android:networkSecurityConfig`
di manifest.

## Pemakaian pertama

1. Pair printer lewat Pengaturan Bluetooth Android seperti biasa. Tidak perlu
   (dan biasanya tidak bisa) menekan "Connect" — itu normal untuk printer SPP.
2. Buka aplikasi, izinkan permintaan Bluetooth.
3. Pengaturan → **Cetak Struk Uji**. Saat pertama kali, muncul daftar perangkat
   paired — pilih printernya. Pilihan itu diingat.
4. Periksa penggaris kolom di struk uji. Kalau terpotong, ubah format kertas di
   Pengaturan (58mm = 32 kolom, 80mm = 48 kolom).

## Kalau bermasalah

| Gejala | Kemungkinan sebab |
|---|---|
| Tombol cetak tidak bereaksi | Halaman dibuka di browser, bukan di aplikasi. Cek badge di Pengaturan: harus "Printer thermal terhubung" |
| "Gagal terhubung ke printer" | Printer mati, jauh, atau sedang dipakai aplikasi lain. Kode sudah mencoba jalur cadangan RFCOMM channel 1 |
| Baris terakhir struk terpotong | Perbesar `Thread.sleep(400)` sebelum socket ditutup |
| Karakter aneh tercetak | Struk sengaja ASCII saja; laporkan bila masih muncul — mungkin butuh codepage lain |
| Kertas tidak terpotong | Wajar bila printer tanpa auto-cutter. Set "Potong Kertas Otomatis" = Tidak |
| Halaman tidak termuat | `POS_URL` salah, atau HTTP diblokir (lihat `network_security_config.xml`) |
