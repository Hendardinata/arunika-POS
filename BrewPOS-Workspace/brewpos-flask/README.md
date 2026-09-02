# Arunika-POS (Flask Backend & Web Dashboard)

Modern Coffee Shop Point of Sales (POS) with CRM, Loyalty, Gamification & Recipe Inventory Management.

---

## Persiapan & Menjalankan Aplikasi

### Linux / WSL

#### 1. Cara Cepat (Menggunakan Script `run_linux.sh`)
```bash
cd BrewPOS-Workspace/brewpos-flask

# Mode Development (Flask built-in server)
./run_linux.sh

# Mode Production / Hosting (Gunicorn WSGI)
./run_linux.sh prod

# Menjalankan Seeder Database
./run_linux.sh seed

# Menjalankan Pengujian (Pytest)
./run_linux.sh test
```

#### 2. Cara Manual (Linux)
```bash
# Buat dan aktifkan Virtual Environment Linux
python3 -m venv --copies venv_linux
source venv_linux/bin/activate

# Pasang dependensi
pip install -r requirements.txt
pip install gunicorn

# Konfigurasi .env (Pastikan driver ODBC sesuai dengan yang terpasang, misal ODBC Driver 18)
# DATABASE_URL=mssql+pyodbc://sa:password@localhost/arunika_caffee?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes

# Jalankan seeder database awal
python seed.py

# Jalankan server development
python run.py

# Atau jalankan hosting production dengan Gunicorn
gunicorn -w 4 -b 0.0.0.0:3001 --timeout 120 "run:app"
```

#### 3. Menjalankan sebagai Background Service (Systemd di Linux)
File unit service telah disiapkan di `brewpos-flask.service`:
```bash
# Salin service file ke systemd (opsional / jika ingin auto-start saat boot)
sudo cp brewpos-flask.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now brewpos-flask.service

# Cek status service
sudo systemctl status brewpos-flask.service
```

---

### Windows (PowerShell / CMD)

#### 1. Aktifkan Virtual Environment (VENV)
```powershell
cd BrewPOS-Workspace/brewpos-flask

# Aktifkan virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Atau jika menggunakan Command Prompt (CMD):
.\venv\Scripts\activate.bat
```

#### 2. Pasang Dependensi
```bash
pip install -r requirements.txt
```

#### 3. Konfigurasi Database (`.env`)
Pastikan connection string MSSQL di file `.env` sudah sesuai:
```env
PORT=3001
# Isi acak, jangan pakai nilai contoh:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
SECRET_KEY=
JWT_SECRET_KEY=
DATABASE_URL=mssql+pyodbc://USER:PASSWORD@localhost/NAMA_DB?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
UPLOAD_FOLDER=app/static/uploads
FLASK_ENV=development
```

#### 4. Inisialisasi & Seeding Database
```bash
python seed.py
```

#### 5. Jalankan Server
```bash
python run.py
```
Aplikasi web dan API siap diakses di: **`http://localhost:3001`**

---

## Tampilan & Antarmuka

Keluarga **Minimalism**: netral putih/abu/hitam dengan **satu** aksen (cokelat
espresso, identitas kafenya). Hierarki dibangun dari tipografi, jarak, dan
perataan -- bukan dari border tebal, gradien, atau bayangan berlapis. Halaman
ini padat data, dan tiap elemen dekoratif bersaing dengan angkanya sendiri.

Semua warna hidup di token `:root` pada `app/static/css/style.css`. **Jangan
menulis heksadesimal langsung** di stylesheet maupun di atribut `style` templat;
pakai `var(--…)`, kalau tidak nilainya tertinggal saat tema disetel ulang.

Tiga pengecualian yang sengaja tidak memakai token:

- Blok `@media print` dan CSS struk termal -- harus hitam-putih agar cocok
  dengan kertas, bukan dengan layar.
- Palet Chart.js -- `<canvas>` tidak mengerti `var(--x)` dan menggambarnya
  sebagai transparan. Pakai `cssVar('--nama')` / `paletGrafik()` dari `app.js`,
  yang membaca nilainya dari `:root` saat dijalankan.

### Tiga penyempurna otomatis di `app.js`

Ketiganya berlaku untuk seluruh halaman dan berjalan ulang lewat satu
`MutationObserver`, karena tabel dan dropdown di sini digambar ulang lewat
`innerHTML` terus-menerus. Tidak ada templat yang perlu disunting.

1. **Dropdown bisa dicari.** Tiap `<select>` dengan **8 pilihan atau lebih**
   otomatis dapat kotak ketik untuk menyaring. `<select>` aslinya tetap di DOM
   dan tetap memegang nilainya, jadi `sel.innerHTML = …`, `sel.value`,
   `onchange`, `FormData`, dan `required` semuanya tetap bekerja apa adanya.
   Paksa dengan `data-searchable`, matikan dengan `data-searchable="off"`.
   Dropdown yang tadinya pendek ikut berubah sendiri begitu datanya bertambah.
2. **Tabel jadi kartu di bawah 640px.** Label tiap sel disalin dari `<thead>`
   ke `td[data-label]`, jadi 26 tabel yang ada -- dan tabel berikutnya -- dapat
   tanpa diminta. Label ditaruh **di atas** nilainya, keduanya berlebar penuh.
   Judul kolom di sini ditulis untuk header tabel lebar ("Nama Bahan Baku /
   Kemasan", "Kontak (Telp / Email)") dan tidak muat di kolom sempit mana pun;
   susunan sisi-sisian selalu berakhir dengan label tiga baris atau tabrakan
   antar baris. Ditumpuk, tidak ada tawar-menawar lebar sama sekali.
3. **Kisi sebaris membungkus di bawah 640px.** Ada 32 tempat yang menulis
   `grid-template-columns` di atribut `style`; di layar 360px itu membuat
   seluruh halaman bisa digeser ke samping. Kisinya diubah jadi baris yang
   membungkus -- bukan ditumpuk satu kolom, karena menumpuk membuat tombol
   kecil (hapus, tambah) memenuhi lebar layar dan nilai rata-kanan menggantung
   sendirian. Pakai kelas `.keep-grid` bila suatu kisi memang harus tetap
   berkolom di layar sempit.

### Pintasan papan ketik (desktop)

| Tombol | Fungsi |
|---|---|
| `Alt` + `1`…`9` | Buka halaman ke-1..9 di menu samping (hanya yang boleh dibuka) |
| `/` atau `Ctrl` + `K` | Fokus ke kotak pencarian halaman ini |
| `Ctrl` + `Enter` | Jalankan tombol utama -- di dalam dialog kalau ada, kalau tidak di halaman |
| `Esc` | Tutup dialog, panel keranjang, atau menu samping |
| `?` | Tampilkan daftar pintasan |

Hanya aktif pada `(pointer: fine)`. Di layar sentuh papan ketik cuma muncul saat
mengisi, dan pintasan huruf tunggal di sana lebih sering salah picu daripada
membantu. Tombol keyboard di topbar adalah pintu masuknya -- pintasan yang tidak
diketahui siapa pun sama saja dengan tidak ada.

Semuanya diturunkan dari DOM yang sudah ada: kotak pencarian dicari lewat
placeholder "Cari" (bukan daftar id, yang akan ketinggalan), tombol utama lewat
`[type=submit]`/`.btn-primary`, dan menu samping lewat tautan yang **terlihat**
-- jadi urutan `Alt`+angka otomatis mengikuti hak akses tiap pengguna.

### Menguji tampilan

Server Flask **menyimpan templat di memori** saat start (`debug=False`), jadi
perubahan pada `.html` tidak terlihat sampai server dijalankan ulang. CSS dan JS
tidak terpengaruh -- keduanya disajikan langsung dari disk dengan `?v=mtime`.

Acuan lebar uji: **360px** (Samsung S10), **820px** (tablet potret), **1440px**
(desktop). Terakhir diperiksa: tidak ada geser horizontal di ketiganya.

## Halaman di Menu Sistem

Dulu satu halaman `/settings` memuat tiga hal sekaligus. Sekarang terpisah supaya
tiap bagian punya alamat sendiri dan izinnya bisa diatur satu per satu:

| Halaman | Alamat | Isi |
|---|---|---|
| Pengaturan Sistem | `/settings` | Profil toko, parameter struk, tutup buku, tes printer |
| Akun & Hak Akses | `/users` | Akun login, izin per-user, matriks hak akses role |
| Manajemen Basis Data | `/database` | Buat & unduh cadangan (Admin/Owner); riwayat & persetujuan restore (Superadmin) |

Untuk basis data yang sudah jalan, `/users` dan `/database` didaftarkan otomatis
saat server start (`db_migrator`). `/users` **mewarisi izin `/settings` apa
adanya** — termasuk daftar khusus per-user — karena di sanalah kelola akun dulu
berada; `/database` dibuka untuk Admin/Owner ke atas. Izin yang sudah pernah diubah
lewat halaman Akun & Hak Akses tidak disentuh.

## Backup & Restore Basis Data

Halamannya sendiri di **Sistem -> Manajemen Basis Data** (`/database`). Izinnya
dibagi menurut satu garis: siapa yang boleh menyentuh **penyimpanan** cadangan,
dan siapa yang cuma boleh mengambil salinan untuk dirinya sendiri.

| Tindakan | Admin/Owner | Superadmin |
|---|---|---|
| Buat & unduh cadangan (tidak disimpan di server) | ya | ya |
| Lihat riwayat, simpan, unduh ulang, hapus | **tidak** | ya |
| Pulihkan (restore) | **mengajukan** | **memutuskan** (setujui / tolak) |

**Kenapa Owner tidak boleh membaca riwayat.** Kalau boleh, ia juga bisa mengunduh
cadangan yang dibuat Superadmin kapan saja — dan tiap `.bak` berisi seluruh isi
basis data, termasuk hash sandi setiap akun. Dengan "buat & unduh", Owner hanya
pernah memegang salinan yang ia buat sendiri saat itu juga, dan server tidak
menyimpan apa pun untuknya.

### Bagaimana unduhannya sampai ke perangkat

Unduhan berjalan **dua langkah**: `POST` membuat cadangan dan mengembalikan
tautan sekali pakai, lalu tautan itu dibuka sebagai **GET biasa**.

Terdengar berputar, tapi ini yang membuatnya bekerja di luar browser desktop.
Cara sebelumnya (`fetch` -> blob -> `<a download>`) mati di WebView Android:
`DownloadListener` — satu-satunya jalan menyerahkan berkas ke pengunduh sistem —
**tidak pernah menyala untuk URL `blob:`**, jadi tombolnya diam saja di aplikasi
kasir. Sebagai GET biasa, tiap platform menanganinya dengan mesinnya sendiri:
`DownloadManager` di Android, pengelola unduhan Safari di iOS, unduhan bawaan di
desktop.

Navigasi tidak bisa membawa header `Authorization`, maka tiketnya: token acak
32 byte, **sekali pakai**, umur 2 menit, di luar `/api/` sehingga middleware auth
tidak perlu dilubangi. Tiket yang kedaluwarsa tanpa pernah ditukar ikut menghapus
berkasnya — itu menutup kasus "tombol ditekan, unduhan tidak pernah dimulai".

Berkas jalur "buat & unduh" **dihapus sebelum responsnya dikirim**, bukan
sesudah. Versi pertama memakai `send_file` + `call_on_close` dan berkasnya
tertinggal — terbukti tiga `.bak` 12 MB menumpuk setelah tiga permintaan. Untuk
berkas seukuran itu yang isinya seluruh basis data, "biasanya terhapus" bukan
jaminan yang cukup. Konsekuensinya berkasnya masuk memori dulu; kalau basis data
tumbuh ke ratusan MB, kembali ke aliran — tapi dengan penghapus yang diuji.

- **Pulihkan** menimpa seluruh basis data dengan isi cadangan. Semua sesi kasir
  yang sedang berjalan terputus, dan langkah ini tidak bisa dibatalkan. Bisa dari
  cadangan yang sudah ada di server (Superadmin), atau dari berkas `.bak` yang
  diunggah.

### Alur persetujuan pemulihan

Restore menimpa seluruh isi toko dan tidak bisa dibatalkan, jadi keputusannya
dipecah **dua tindakan oleh dua orang**:

1. Admin/Owner **mengajukan** — memilih berkas riwayat atau mengunggah `.bak`,
   disertai **alasan** (minimal 10 karakter). Satu permintaan menggantung pada
   satu waktu; antrean restore tidak masuk akal karena yang kedua akan memulihkan
   di atas hasil yang pertama.
2. Superadmin melihatnya di **halamannya sendiri** (bagian *Permintaan Menunggu
   Persetujuan* di `/database`) lalu **Setujui & Pulihkan** atau **Tolak**.
   Menyetujui langsung menjalankan pemulihannya — permintaan yang sudah disetujui
   tapi belum dijalankan adalah izin menghapus isi toko yang menganggur.

Pemohon boleh membatalkan permintaannya sendiri selama belum diputus, dan
permintaan yang menganggur lebih dari **24 jam** ditutup otomatis beserta berkas
unggahannya.

**Tidak ada sandi yang berpindah tangan.** Masing-masing bertindak sambil masuk
sebagai dirinya sendiri, dan catatan aktivitas menyebut dua nama: yang mengajukan
dan yang menyetujui. Superadmin tetap bisa memulihkan langsung tanpa lewat
permintaan — ia memang yang menyetujui, jadi mengajukan kepada dirinya sendiri
hanya menambah langkah tanpa menambah pengaman.

Berkas `.bak` yang diunggah menunggu di server sampai diputus, disembunyikan dari
riwayat dan **tidak** ikut disapu penyapu berkas kerja satu jam. Ia dibuang
begitu permintaannya ditolak, dibatalkan, kedaluwarsa, atau selesai dipulihkan.

Untuk basis data yang sudah jalan, `/database` dibuka untuk Admin/Owner otomatis
saat server start -- **sekali saja**, ditandai di `SystemSettings`. Kalau nanti
ditutup lagi lewat Matriks Hak Akses, pilihan itu tidak akan ditimpa restart.

Berkas `.bak` berisi seluruh isi basis data, **termasuk hash sandi setiap akun**.
Itu sebabnya jalur cadangan berhenti di Admin/Owner dan tidak turun lebih jauh.

Berkas `.bak` **ditulis oleh SQL Server**, bukan oleh Flask. Karena itu foldernya
harus bisa ditulis akun layanan SQL Server sekaligus dibaca proses Flask:

- Bawaannya `backups/` di dalam folder aplikasi ini. Saat pertama dipakai,
  aplikasi memberi akun layanan SQL Server izin tulis ke folder itu (`icacls`,
  tidak perlu hak administrator karena foldernya milik proses ini).
- Folder backup bawaan SQL Server sengaja **tidak** dipakai: letaknya di dalam
  `Program Files` dan proses Flask biasa ditolak membacanya, sehingga berkasnya
  tidak akan pernah bisa diunduh.
- Kalau perlu folder lain (mis. SQL Server di mesin terpisah, lewat share
  jaringan), setel `DB_BACKUP_DIR` di `.env`.

Folder `backups/` dan seluruh `*.bak` sudah masuk `.gitignore` — repo ini publik.

> **Restore belum diuji terhadap instance nyata.** Jalur backup sudah diverifikasi
> menghasilkan `.bak` yang sah; jalur restore ditulis lengkap tapi belum pernah
> dijalankan. Uji pertama sebaiknya di basis data salinan, bukan basis data toko.

## Menjalankan Test

Test berjalan di atas SQLite sementara, jadi tidak menyentuh database MSSQL sama sekali
dan aman diulang kapan saja.

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest
```

Cakupan: gerbang autentikasi `/api/*`, aturan harga & diskon sisi server, pemotongan dan
pengembalian stok bahan saat void, serta pemisahan laporan penjualan sah dan void.

---

## Akun Demo Default

Dibuat otomatis oleh seeder. Password hanya di-generate saat akun belum ada — mengganti
password lewat UI tidak akan tertimpa saat server restart.

| Username | Password | Role |
|---|---|---|
| `superadmin` | `12qwaszx` | SUPERADMIN |
| `owner` | `12qwaszx` | ADMIN |
| `headbar` | `12qwaszx` | HEADBAR |
| `kasir` | `12qwaszx` | CASHIER |

> **Ganti keempat password ini sebelum server dipakai toko.** Nilai default ada di
> `db_seeder.py` dan repo ini publik, jadi selama belum diganti siapa pun yang bisa
> menjangkau alamat server bisa masuk sebagai `superadmin`.

---

## Catatan Otorisasi

- Seluruh endpoint `/api/*` memerlukan JWT, kecuali `/api/auth/login`.
- Harga per item selalu diambil dari tabel `Menu`; harga kiriman client diabaikan.
- Nilai diskon reward berasal dari `Reward.discountValue`, bukan dari body request.
- Diskon manual tanpa reward dan pembatalan (void) transaksi memerlukan role HEADBAR ke atas.
- Jatah gratis karyawan dibatasi sisa `dailyQuota` yang dihitung server, dalam satuan cup.
