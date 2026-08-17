"""
Kosongkan data operasional menjelang go-live.

    python reset_data.py                       # HANYA menampilkan yang akan dihapus
    python reset_data.py --yes                 # benar-benar menghapus
    python reset_data.py --keep-member Rifqi   # member yang dipertahankan (bisa diulang)

Yang DIHAPUS  : transaksi, sesi kas, serah terima, pengeluaran, mutasi stok,
                opname, absensi, log sistem, omzet lama, progres quest/badge,
                dan semua member selain yang disebut --keep-member.

Yang DIPERTAHANKAN : pengguna, menu, kategori, resep, bahan, reward, quest,
                     badge, kategori pengeluaran, dan seluruh pengaturan.

Stok dan harga beli setiap bahan dinolkan -- stok fisik belum dirangkum, dan
harga 0 lebih jujur daripada harga lama yang belum tentu berlaku.

Bawaannya HANYA menampilkan. Tanpa --yes tidak ada satu baris pun yang dihapus.
"""
import argparse
import sys

from app import create_app
from app.extensions import db
from app.models.attendance import Attendance, ShiftHandover
from app.models.customer import Customer, CustomerBadge, CustomerQuest
from app.models.expense import Expense
from app.models.historical_sales import HistoricalSales
from app.models.inventory import DailyOpname, DailyOpnameItem, InventoryItem, InventoryLog
from app.models.shift import Shift
from app.models.system_log import SystemLog
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User

# Urutan mengikuti kunci asing: anak lebih dulu, induk belakangan. Salah urutan
# di MSSQL berarti gagal di tengah jalan dengan sebagian data sudah terhapus.
URUTAN_HAPUS = [
    ('Rincian transaksi', TransactionItem),
    ('Transaksi', Transaction),
    ('Serah terima sesi', ShiftHandover),
    ('Pengeluaran', Expense),
    ('Rincian opname', DailyOpnameItem),
    ('Opname', DailyOpname),
    ('Mutasi stok', InventoryLog),
    ('Sesi kas', Shift),
    ('Absensi', Attendance),
    ('Omzet lama', HistoricalSales),
    ('Progres quest member', CustomerQuest),
    ('Badge member', CustomerBadge),
    ('Log sistem', SystemLog),
]


def _member_dipertahankan(nama_dipertahankan):
    """Member yang namanya disebut, tidak peduli besar-kecil hurufnya."""
    if not nama_dipertahankan:
        return []
    lower = [n.strip().lower() for n in nama_dipertahankan if n.strip()]
    return [c for c in Customer.query.all() if (c.nickname or '').lower() in lower]


def reset_data(keep_members, yakin=False, app=None):
    app = app or create_app()
    with app.app_context():
        disimpan = _member_dipertahankan(keep_members)
        id_disimpan = {c.id for c in disimpan}

        diminta = {n.strip().lower() for n in keep_members if n.strip()}
        ketemu = {(c.nickname or '').lower() for c in disimpan}
        hilang = diminta - ketemu

        member_dihapus = Customer.query.filter(~Customer.id.in_(id_disimpan)).count() \
            if id_disimpan else Customer.query.count()

        print('Akan DIHAPUS:')
        total = 0
        for nama, model in URUTAN_HAPUS:
            n = model.query.count()
            total += n
            print(f"  {nama:22} {n:>7}")
        print(f"  {'Member':22} {member_dihapus:>7}")
        total += member_dihapus

        bahan = InventoryItem.query.count()
        print(f"\nDinolkan stok & harganya : {bahan} bahan (barisnya tetap ada)")
        print('Dipertahankan            : pengguna, menu, kategori, resep, bahan, '
              'reward, quest, badge, kategori pengeluaran, pengaturan')
        print(f"Member dipertahankan     : "
              + (', '.join(c.nickname for c in disimpan) if disimpan else '(tidak ada)'))
        print(f"Pengguna                 : {User.query.count()} akun, tidak disentuh")

        # Penjaga ini melindungi member yang sudah ada. Kalau memang belum ada
        # member sama sekali, tidak ada yang perlu dilindungi -- menolak jalan di
        # database kosong hanya bikin bingung.
        if hilang and Customer.query.count() > 0:
            # Berhenti, jangan diteruskan: kemungkinan besar salah ketik nama, dan
            # kalau diteruskan member yang mau diselamatkan justru ikut terhapus.
            print(f"\nBERHENTI: member tidak ditemukan -> {', '.join(sorted(hilang))}")
            print('Periksa ejaannya. Tidak ada yang dihapus.')
            return 1

        if not yakin:
            print(f"\nTidak ada yang dihapus ({total} baris akan terhapus kalau dijalankan).")
            print('Ulangi dengan --yes kalau memang yakin.')
            return 1

        for _, model in URUTAN_HAPUS:
            model.query.delete(synchronize_session=False)

        if id_disimpan:
            Customer.query.filter(~Customer.id.in_(id_disimpan)).delete(synchronize_session=False)
        else:
            Customer.query.delete(synchronize_session=False)

        # Stok fisik belum dirangkum; harga lama belum tentu masih berlaku.
        for item in InventoryItem.query.all():
            item.stock = 0.0
            item.costPerUnit = 0.0

        db.session.commit()

        print(f"\nSelesai. {total} baris dihapus, {bahan} bahan dinolkan.")
        print('Langkah berikutnya: isi harga beli tiap bahan, lalu Opname untuk '
              'menetapkan stok awal.')
        return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Kosongkan data operasional menjelang go-live.')
    # default lewat "or", bukan default=[...]: dengan action='append' argparse
    # menambahkan ke daftar bawaan alih-alih menggantinya, jadi --keep-member Budi
    # akan diam-diam ikut menyimpan Rifqi juga.
    p.add_argument('--keep-member', action='append',
                   help='nickname member yang dipertahankan (boleh diulang, bawaan: Rifqi)')
    p.add_argument('--yes', action='store_true', help='benar-benar hapus')
    a = p.parse_args()
    sys.exit(reset_data(a.keep_member or ['Rifqi'], a.yes))
