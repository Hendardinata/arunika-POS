<div align="center">
  <h1>☕ Arunika-POS</h1>
  <p><strong>Every Cup Has A Story.</strong></p>
  <p>Modern Point of Sales (POS) with integrated CRM, Loyalty Programs, and Gamification for Coffee Shops.</p>

  <img src="https://img.shields.io/badge/Flutter-02569B?style=for-the-badge&logo=flutter&logoColor=white" alt="Flutter" />
  <img src="https://img.shields.io/badge/Node.js-339933?style=for-the-badge&logo=nodedotjs&logoColor=white" alt="Node.js" />
  <img src="https://img.shields.io/badge/Prisma-3982CE?style=for-the-badge&logo=Prisma&logoColor=white" alt="Prisma" />
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
</div>

<br/>

## 📖 Tentang Arunika-POS

Arunika-POS bukan sekadar aplikasi kasir (POS) biasa. Sebagian besar aplikasi POS berhenti pada titik di mana pelanggan selesai membayar, sehingga tidak ada interaksi lanjutan. Arunika-POS memecahkan masalah ini dengan membangun **hubungan jangka panjang dengan pelanggan**. 

Kami menggabungkan fitur **POS, Customer Relationship Management (CRM), Program Loyalitas, dan Gamifikasi** dalam satu ekosistem. Setiap pesanan menjadi sebuah petualangan (*Coffee Journey*) yang memberikan poin, membuka *badges* (pencapaian), dan misi harian untuk menarik pelanggan datang kembali.

---

## ✨ Fitur Utama

- 🛒 **Smart Checkout & Point of Sales**: Proses transaksi kasir yang cepat, mudah dipahami, dengan fitur Receipt digital/cetak.
- 🎯 **Loyalty & CRM**: Setiap transaksi menghasilkan poin. Owner dapat mengatur masa kedaluwarsa poin dan *tier/level* membership.
- 🎮 **Gamification System**: 
  - **Coffee Passport**: Dorongan untuk mencoba semua menu.
  - **Achievements & Badges**: Unlock pencapaian seperti dalam game.
  - **Daily Quest & Streak**: Misi harian dan reward untuk kedatangan berturut-turut.
  - **Mystery Box & Lucky Spin**: Hadiah kejutan.
- 📊 **Analytics Dashboard**: Pemantauan metrik bisnis secara *real-time* seperti *Repeat Customer Rate*, Transaksi Rata-rata, dan Pemasukan Bulanan.
- 📱 **Multi-Platform Support**: Tersedia untuk Web Dashboard dan Aplikasi Mobile (Android/iOS Tablet & Smartphone).

---

## 🏗️ Struktur Proyek

Proyek ini dibangun menggunakan struktur Workspace (Multi-repository / Monorepo style) yang terdiri dari:

```text
Arunika-POS-Workspace/
├── arunika-pos-backend/   # REST API backend (Node.js, TypeScript, Prisma)
├── arunika-pos-web/       # Dashboard Admin berbasis Web
└── arunika_pos_mobile/    # Aplikasi Kasir Mobile / Tablet (Flutter)
```
*(Catatan: Jika folder lokal Anda masih bernama `BrewPOS-Workspace` dsb., Anda bisa menyesuaikan path saat instalasi di bawah)*

---

## 🚀 Kebutuhan Sistem (Prerequisites)

Sebelum menjalankan proyek ini, pastikan Anda telah menginstal perangkat lunak berikut:

1. **[Node.js](https://nodejs.org/en/)** (versi 16 atau yang lebih baru) - Untuk Backend & Web.
2. **[Flutter SDK](https://docs.flutter.dev/get-started/install)** (versi 3.x) - Untuk Mobile App.
3. **[PostgreSQL](https://www.postgresql.org/)** - Sebagai Database utama.
4. **Git** - Untuk version control.

---

## 🛠️ Cara Instalasi & Penggunaan

### 1. Setup Database (PostgreSQL)
Buat database baru di PostgreSQL Anda (misalnya dengan nama `arunika_pos_db`). Pastikan Anda mengingat `username` dan `password` database Anda.

### 2. Setup Backend (`arunika-pos-backend`)
Backend bertugas sebagai pusat data dan API untuk aplikasi Mobile maupun Web.

```bash
# Masuk ke direktori backend (Sesuaikan dengan nama folder Anda)
cd Arunika-POS-Workspace/arunika-pos-backend

# Instalasi dependensi
npm install

# Konfigurasi Environment Variables
# Copy file .env.example menjadi .env (atau buat file .env baru) dan sesuaikan:
# DATABASE_URL="postgresql://user:password@localhost:5432/arunika_pos_db"

# Jalankan migrasi Prisma ke Database
npx prisma db push
# (atau npx prisma migrate dev jika Anda menggunakan migration tracking)

# Menjalankan server backend
npm run dev
```

### 3. Setup Web Dashboard (`arunika-pos-web`)
Dashboard digunakan oleh Owner untuk memantau analitik dan mengatur produk/menu.

```bash
# Buka terminal baru, masuk ke direktori web
cd Arunika-POS-Workspace/arunika-pos-web

# Instalasi dependensi
npm install

# Menjalankan server web development
npm run dev
```

### 4. Setup Mobile POS (`arunika_pos_mobile`)
Aplikasi yang digunakan oleh kasir/barista di Coffee Shop (Tablet/Smartphone).

```bash
# Buka terminal baru, masuk ke direktori mobile
cd Arunika-POS-Workspace/arunika_pos_mobile

# Ambil semua dependensi Flutter
flutter pub get

# Konfigurasi URL API
# Pastikan Base URL pada aplikasi Flutter mengarah ke IP Backend Anda (contoh: http://192.168.1.x:3000)

# Menjalankan aplikasi mobile (pastikan emulator jalan atau device tersambung)
flutter run
```

---

## 💻 Tech Stack Detail

| Komponen | Teknologi |
| :--- | :--- |
| **Mobile App (POS)** | Flutter, Riverpod (State Management), GoRouter |
| **Web Dashboard** | React / Next.js / Vue (Frontend web framework) |
| **Backend API** | Node.js, Express/FastAPI, Prisma ORM, TypeScript |
| **Database** | PostgreSQL |
| **Authentication** | JWT (JSON Web Tokens) |
| **Architecture** | Clean Architecture, SOLID Principles |

---

## 🤝 Kontribusi

Jika Anda ingin berkontribusi:
1. *Fork* repository ini.
2. Buat branch fitur baru (`git checkout -b fitur-baru-anda`).
3. Lakukan commit perubahan Anda (`git commit -m 'Menambahkan fitur x'`).
4. Push ke branch (`git push origin fitur-baru-anda`).
5. Buat sebuah *Pull Request*.

---

<div align="center">
  <p>Dibuat dengan ❤️ untuk kemajuan UMKM Kopi.</p>
</div>
