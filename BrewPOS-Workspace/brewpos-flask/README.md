# ☕ Arunika-POS (Flask Backend & Web Dashboard)

Modern Coffee Shop Point of Sales (POS) with CRM, Loyalty, Gamification & Recipe Inventory Management.

---

## 🚀 Persiapan & Menjalankan Aplikasi

### 1. Aktifkan Virtual Environment (VENV)
```powershell
# Masuk ke direktori
cd BrewPOS-Workspace/brewpos-flask

# Aktifkan virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Atau jika menggunakan Command Prompt (CMD):
.\venv\Scripts\activate.bat
```

### 2. Konfigurasi Database (`.env`)
Pastikan connection string MSSQL di file `.env` sudah sesuai:
```env
PORT=3001
SECRET_KEY=arunika_pos_secret_key_super_secure_2026
JWT_SECRET_KEY=fallback_secret_for_development_only
DATABASE_URL=mssql+pyodbc://sa:12qwaszx#DB@localhost/arunika_caffee?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
UPLOAD_FOLDER=app/static/uploads
FLASK_ENV=development
```

### 3. Inisialisasi & Seeding Database
Jalankan seeder untuk membuat 23 tabel dan data awal di database MSSQL:
```bash
python seed.py
```

### 4. Jalankan Server
```bash
python run.py
```
Aplikasi web dan API siap diakses di: **`http://localhost:3001`**

---

## 🔑 Akun Demo Default
- **Owner / Admin**: `admin` / `123`
- **Kasir (Shift Pagi)**: `kasir` / `123`
