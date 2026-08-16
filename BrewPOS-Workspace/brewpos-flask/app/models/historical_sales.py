from datetime import datetime
from app.extensions import db


class HistoricalSales(db.Model):
    """
    Omzet harian dari masa sebelum aplikasi ini dipakai.

    Toko sudah berjualan lebih dulu, dan catatan lamanya hanya sampai tingkat
    "tanggal sekian omzetnya sekian" -- tidak ada rincian menu, tidak ada nota
    per transaksi. Karena itu baris ini sengaja TIDAK disimpan sebagai
    Transaction:

      - tanpa rincian menu, laporan profitabilitas per menu akan berbohong
      - potong stok otomatis akan menggerus stok hari ini, padahal stok fisik
        sekarang sudah mencerminkan penjualan lama itu
      - poin & XP member ikut terhitung dua kali
      - sesi kas jadi tidak cocok karena uangnya tidak pernah masuk laci hari ini

    Jadi tabel ini hanya menyumbang angka omzet ke laporan pendapatan, dan tidak
    menyentuh apa pun yang lain.
    """
    __tablename__ = 'HistoricalSales'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Satu baris per tanggal; input ulang tanggal yang sama = perbaikan, bukan tambahan.
    date = db.Column(db.Date, unique=True, nullable=False)
    totalAmount = db.Column(db.Integer, nullable=False, default=0)
    # Opsional: kalau catatan lamanya ikut menyebut berapa struk hari itu.
    transactionCount = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'totalAmount': self.totalAmount,
            'transactionCount': self.transactionCount,
            'notes': self.notes,
        }
