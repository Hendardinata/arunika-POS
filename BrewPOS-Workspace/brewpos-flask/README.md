# Arunika-POS (Flask Backend & Web Dashboard)

Modern Coffee Shop Point of Sales (POS) with CRM, Loyalty, Gamification & Recipe Inventory Management.

---

## Persiapan & Menjalankan Aplikasi

### 1. Aktifkan Virtual Environment (VENV)
```powershell
# Masuk ke direktori
cd BrewPOS-Workspace/brewpos-flask

# Aktifkan virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Atau jika menggunakan Command Prompt (CMD):
.\venv\Scripts\activate.bat
```

### 2. Pasang Dependensi
```bash
pip install -r requirements.txt
```

### 3. Konfigurasi Database (`.env`)
Pastikan connection string MSSQL di file `.env` sudah sesuai:
```env
PORT=3001
SECRET_KEY=ganti_dengan_nilai_acak_yang_panjang
JWT_SECRET_KEY=ganti_dengan_nilai_acak_yang_panjang
DATABASE_URL=mssql+pyodbc://sa:password@localhost/arunika_caffee?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
UPLOAD_FOLDER=app/static/uploads
FLASK_ENV=development
```

### 4. Inisialisasi & Seeding Database
Jalankan seeder untuk membuat tabel dan data awal di database MSSQL:
```bash
python seed.py
```

### 5. Jalankan Server
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
| `superadmin` | `superadmin123` | SUPERADMIN |
| `owner` | `owner123` | ADMIN |
| `headbar` | `headbar123` | HEADBAR |
| `kasir` | `kasir123` | CASHIER |

---

## Catatan Otorisasi

- Seluruh endpoint `/api/*` memerlukan JWT, kecuali `/api/auth/login`.
- Harga per item selalu diambil dari tabel `Menu`; harga kiriman client diabaikan.
- Nilai diskon reward berasal dari `Reward.discountValue`, bukan dari body request.
- Diskon manual tanpa reward dan pembatalan (void) transaksi memerlukan role HEADBAR ke atas.
- Jatah gratis karyawan dibatasi sisa `dailyQuota` yang dihitung server, dalam satuan cup.
