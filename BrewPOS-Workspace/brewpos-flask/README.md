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
SECRET_KEY=arunika_pos_secret_key_super_secure_2026
JWT_SECRET_KEY=fallback_secret_for_development_only
DATABASE_URL=mssql+pyodbc://sa:12qwaszx#DB@localhost/arunika_caffee?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
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

> Ganti password ini sebelum dipakai di lingkungan produksi.

---

## Catatan Otorisasi

- Seluruh endpoint `/api/*` memerlukan JWT, kecuali `/api/auth/login`.
- Harga per item selalu diambil dari tabel `Menu`; harga kiriman client diabaikan.
- Nilai diskon reward berasal dari `Reward.discountValue`, bukan dari body request.
- Diskon manual tanpa reward dan pembatalan (void) transaksi memerlukan role HEADBAR ke atas.
- Jatah gratis karyawan dibatasi sisa `dailyQuota` yang dihitung server, dalam satuan cup.
