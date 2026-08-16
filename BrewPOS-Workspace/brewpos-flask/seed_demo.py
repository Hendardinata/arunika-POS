"""
Data contoh pemakaian nyata: penjualan, member, pembelian bahan, seduhan base
espresso, sesi kas, dan pengeluaran selama beberapa hari ke belakang.

    python seed_demo.py                 # 14 hari terakhir
    python seed_demo.py --days 30       # rentang lain
    python seed_demo.py --seed 7        # angka acak yang berbeda
    python seed_demo.py --force         # tetap jalan walau sudah ada transaksi

Bedanya dengan seed.py: berkas itu mengisi master data (user, menu, kategori,
bahan) dan harus tetap sama setiap kali dijalankan. Yang di sini sengaja acak,
untuk mengisi laporan dan grafik supaya kelihatan bagaimana sistem berperilaku
dengan data yang ramai.

Skrip ini hanya MENAMBAH baris, tidak pernah menghapus apa pun. Kalau database
sudah punya transaksi, skrip berhenti kecuali dijalankan dengan --force -- data
demo yang tercampur ke penjualan asli akan merusak laporan.
"""
import argparse
import random
import sys
from datetime import datetime, timedelta

from app import create_app
from app.extensions import db
from app.models.customer import Customer
from app.models.expense import Expense, ExpenseCategory
from app.models.inventory import InventoryItem, InventoryLog
from app.models.menu import Menu, RecipeIngredient
from app.models.shift import Shift
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from app.services.inventory_service import deduct_ingredients_for_order

NAMA_DEPAN = ['Rifqi', 'Ayu', 'Bagus', 'Citra', 'Dimas', 'Eka', 'Fajar', 'Gita', 'Hana',
              'Indra', 'Joko', 'Kirana', 'Lukman', 'Maya', 'Nanda', 'Oka', 'Putri',
              'Rama', 'Sari', 'Tio', 'Umar', 'Vina', 'Wawan', 'Yuda', 'Zahra']

# Jam ramai kedai kopi: pagi sebelum kerja, lalu sore menjelang tutup.
BOBOT_JAM = {8: 3, 9: 5, 10: 6, 11: 4, 12: 5, 13: 4, 14: 3,
             15: 4, 16: 6, 17: 7, 18: 6, 19: 5, 20: 3, 21: 2}

PENGELUARAN_RUTIN = [
    ('Token listrik', 50000, 150000),
    ('Galon air isi ulang', 18000, 25000),
    ('Gas LPG 3kg', 20000, 25000),
    ('Sabun cuci & tisu', 15000, 45000),
    ('Es batu kristal', 20000, 60000),
]


def _jam_acak(rng, tanggal):
    jam = rng.choices(list(BOBOT_JAM), weights=list(BOBOT_JAM.values()))[0]
    waktu = tanggal.replace(hour=jam, minute=rng.randrange(60), second=rng.randrange(60),
                            microsecond=0)
    # Hari terakhir adalah hari ini: jam sibuk sore hari belum terjadi. Tanpa
    # penjepit ini laporan "penjualan hari ini" memuat transaksi masa depan.
    return min(waktu, datetime.utcnow())


def _pastikan_member(rng, jumlah=24):
    """
    Identitas member cukup salah satu: nomor HP ATAU email. Nickname boleh kembar,
    jadi sengaja ada beberapa nama yang sama untuk menguji tampilan daftar member.
    """
    sudah = Customer.query.count()
    if sudah >= jumlah:
        return Customer.query.all()

    for i in range(jumlah - sudah):
        nama = rng.choice(NAMA_DEPAN)
        c = Customer(nickname=nama, points=0, xp=0, level=1, streakCount=0,
                     customerType='REGULAR')
        # Sebagian pakai HP, sebagian email, tidak ada yang wajib punya keduanya.
        if rng.random() < 0.65:
            c.phone = '08' + ''.join(str(rng.randrange(10)) for _ in range(10))
        else:
            c.email = f"{nama.lower()}{rng.randrange(10, 99)}@gmail.com"
        # Beberapa karyawan dengan jatah minum harian
        if i < 3:
            c.customerType = 'EMPLOYEE'
            c.dailyQuota = rng.choice([1, 2])
        db.session.add(c)

    db.session.commit()
    return Customer.query.all()


def _pastikan_harga_bahan(rng, admin):
    """Bahan tanpa harga beli bikin HPP nol dan margin terlihat 100%. Belikan dulu."""
    kategori = ExpenseCategory.query.filter(ExpenseCategory.name.like('%Bahan%')).first() \
        or ExpenseCategory.query.first()

    for item in InventoryItem.query.filter(InventoryItem.isActive == True).all():  # noqa: E712
        if (item.costPerUnit or 0) > 0:
            continue
        # Kisaran harga per satuan yang masuk akal untuk tiap jenis satuan.
        per_satuan = {'gram': (120, 400), 'g': (120, 400), 'ml': (8, 40),
                      'pcs': (400, 2500), 'shot': (2000, 4000)}.get(item.unit, (500, 3000))
        harga = rng.randrange(*per_satuan)
        jumlah = rng.choice([500, 1000, 2000]) if item.unit in ('gram', 'g', 'ml') else rng.choice([50, 100, 200])
        total = harga * jumlah

        item.costPerUnit = float(harga)
        item.stock = (item.stock or 0) + jumlah
        db.session.add(InventoryLog(itemId=item.id, quantity=jumlah, type='IN',
                                    costPerUnit=float(harga), totalCost=float(total),
                                    supplier='Supplier Demo',
                                    notes=f"Pembelian awal {item.name}"))
        if kategori:
            db.session.add(Expense(amount=total, date=datetime.utcnow(), categoryId=kategori.id,
                                   userId=admin.id, paymentSource='CASH_DRAWER',
                                   notes=f"Pembelian {jumlah} {item.unit} {item.name}"))
    db.session.commit()


def _restok_bila_menipis(rng, admin, kategori, tanggal):
    """
    Penjualan menggerus stok tiap hari. Tanpa restok, akhir rentang demo semua
    bahan minus -- data yang terlihat rusak dan tidak bisa dipakai memperagakan
    peringatan stok menipis maupun opname.

    Base Espresso dilewati: isinya datang dari seduhan, bukan dari supplier.
    """
    for item in InventoryItem.query.filter(InventoryItem.isActive == True).all():  # noqa: E712
        if item.name == 'Base Espresso':
            continue

        # Kecepatan pakai kemarin, bukan minStock, yang menentukan kapan belanja
        # dan sebanyak apa. minStock diisi sekali saat master bahan dibuat dan
        # tidak tahu apa-apa soal seramai apa jualannya: bahan yang lari 6 liter
        # sehari tetap dianggap aman di angka 500 ml.
        kemarin = db.session.query(db.func.sum(InventoryLog.quantity)).filter(
            InventoryLog.itemId == item.id,
            InventoryLog.type == 'OUT',
            InventoryLog.createdAt >= tanggal - timedelta(days=1)
        ).scalar() or 0

        # Belanja kalau sisa stok tidak jelas cukup untuk hari ini. Memakai
        # minStock sebagai pemicu membuat stok merembes minus: sisa 1 gram di
        # atas minimum dianggap aman, lalu habis sebelum tengah hari.
        aman = max((item.minStock or 0), kemarin * 1.5)
        if (item.stock or 0) > aman:
            continue

        paket = rng.choice([500, 1000]) if item.unit in ('gram', 'g', 'ml') else rng.choice([50, 100])
        # Beli utuh per paket sampai cukup untuk sekitar 4 hari.
        target = max(kemarin * 4, (item.minStock or 0) * 3, paket)
        jumlah = 0
        while (item.stock or 0) + jumlah < target:
            jumlah += paket

        # Harga naik-turun sedikit tiap belanja, seperti harga pasar sungguhan.
        harga = round((item.costPerUnit or 1) * rng.uniform(0.95, 1.12), 2)
        total = int(harga * jumlah)

        item.stock = (item.stock or 0) + jumlah
        item.costPerUnit = harga
        db.session.add(InventoryLog(itemId=item.id, quantity=jumlah, type='IN',
                                    costPerUnit=harga, totalCost=float(total),
                                    supplier=rng.choice(['CV Kopi Nusantara', 'Toko Sembako Jaya',
                                                         'Distributor Susu Segar']),
                                    notes=f"Restok {item.name}", createdAt=tanggal))
        if kategori:
            db.session.add(Expense(amount=total, date=tanggal, categoryId=kategori.id,
                                   userId=admin.id, paymentSource='CASH_DRAWER',
                                   notes=f"Restok {jumlah} {item.unit} {item.name}"))


def _siapkan_base_espresso():
    base = InventoryItem.query.filter_by(name='Base Espresso').first()
    if not base:
        base = InventoryItem(name='Base Espresso', unit='ml', stock=0.0, minStock=200.0)
        db.session.add(base)
        db.session.flush()

    kopi = (InventoryItem.query.filter(InventoryItem.name.like('%Kopi%'),
                                       InventoryItem.unit.in_(['gram', 'g'])).first()
            or InventoryItem.query.filter(InventoryItem.unit.in_(['gram', 'g'])).first())
    return base, kopi


def _seduh_base_espresso(rng, base, kopi, waktu):
    """
    Contoh pemakaian fitur produksi. Takaran sengaja tidak tetap -- di dapur
    memang berubah tergantung situasi, dan justru itu yang mau ditunjukkan:
    harga per ml base ikut bergerak, tapi rata-rata tertimbang menahannya.
    """
    if not kopi:
        return False

    gram = rng.choice([50, 60, 70, 80])
    hasil = gram * rng.choice([4, 5, 5, 6])     # rendemen bervariasi
    modal = gram * (kopi.costPerUnit or 0)

    kopi.stock = (kopi.stock or 0) - gram
    db.session.add(InventoryLog(itemId=kopi.id, quantity=gram, type='OUT',
                                costPerUnit=kopi.costPerUnit or 0.0, totalCost=modal,
                                notes=f"Produksi Base Espresso: {hasil} ml", createdAt=waktu))

    nilai_lama = (base.stock or 0.0) * (base.costPerUnit or 0.0)
    base.stock = (base.stock or 0.0) + hasil
    base.costPerUnit = round((nilai_lama + modal) / base.stock, 4) if base.stock else 0.0
    db.session.add(InventoryLog(itemId=base.id, quantity=hasil, type='IN',
                                costPerUnit=round(modal / hasil, 4), totalCost=modal,
                                notes=f"Produksi Base Espresso: dari {gram} g {kopi.name}",
                                createdAt=waktu))
    return True


def _buat_transaksi(rng, waktu, menus, members, kasir, shift, urut):
    banyak_item = rng.choices([1, 2, 3, 4], weights=[45, 33, 15, 7])[0]
    pilihan = rng.sample(menus, min(banyak_item, len(menus)))

    subtotal = 0
    baris = []
    for m in pilihan:
        qty = rng.choices([1, 2, 3], weights=[75, 20, 5])[0]
        subtotal += m.price * qty
        baris.append((m, qty))

    # Diskon hanya sesekali, seperti di kasir sungguhan.
    diskon = 0
    if rng.random() < 0.12:
        diskon = min(subtotal, rng.choice([5000, 10000, 20000]))

    total = subtotal - diskon
    member = rng.choice(members) if rng.random() < 0.55 else None
    if member is None:
        member = next((c for c in members if c.nickname == 'Guest'), None) or members[0]

    tx = Transaction(
        transactionCode=f"TR{waktu.strftime('%Y%m%d')}{urut:06d}",
        subTotal=subtotal,
        # Harga menu sudah termasuk pajak, jadi pajaknya diurai balik dari total.
        taxAmount=int(round(total * 11 / 111)),
        discountAmount=diskon,
        totalAmount=total,
        pointsEarned=total // 1000,
        paymentMethod=rng.choices(['CASH', 'QRIS', 'DEBIT'], weights=[55, 35, 10])[0],
        status='COMPLETED',
        customerId=member.id,
        shiftId=shift.id,
        userId=kasir.id,
        createdAt=waktu,
    )
    db.session.add(tx)
    db.session.flush()

    for m, qty in baris:
        db.session.add(TransactionItem(transactionId=tx.id, menuId=m.id, quantity=qty,
                                       price=m.price, discountAmount=0, hpp=m.hpp or 0))

    member.points = (member.points or 0) + tx.pointsEarned
    member.xp = (member.xp or 0) + tx.pointsEarned
    member.lastVisitDate = waktu

    # Pakai jalur potong stok yang sungguhan, bukan menyalin logikanya -- kalau
    # resep berubah, data demo ikut benar dengan sendirinya.
    log_terakhir = db.session.query(db.func.max(InventoryLog.id)).scalar() or 0
    deduct_ingredients_for_order(tx.id, [{'menuId': m.id, 'quantity': q} for m, q in baris])

    # Layanan itu memakai createdAt bawaan (waktu sekarang), padahal transaksi
    # ini bertanggal mundur. Tanpa dicap ulang, seluruh mutasi stok menumpuk di
    # satu detik yang sama dan riwayat inventori jadi tidak terbaca.
    db.session.query(InventoryLog).filter(InventoryLog.id > log_terakhir).update(
        {InventoryLog.createdAt: waktu}, synchronize_session=False)
    return tx


def seed_demo(days, seed, force, app=None):
    rng = random.Random(seed)
    # app bisa disuntik dari tes supaya skrip ini teruji tanpa menyentuh
    # database sungguhan.
    app = app or create_app()

    with app.app_context():
        sudah = Transaction.query.count()
        if sudah and not force:
            print(f"BERHENTI: sudah ada {sudah} transaksi di database ini.\n"
                  "Data demo yang tercampur ke penjualan asli akan merusak laporan.\n"
                  "Kalau memang ini database uji coba, jalankan ulang dengan --force.")
            return 1

        menus = Menu.query.filter(Menu.isActive == True).all()  # noqa: E712
        if not menus:
            print("BERHENTI: belum ada menu. Jalankan `python seed.py` lebih dulu.")
            return 1

        kasir_semua = User.query.filter(User.role.in_(['CASHIER', 'HEADBAR', 'SUPERADMIN'])).all()
        admin = User.query.filter_by(role='SUPERADMIN').first() or kasir_semua[0]
        if not kasir_semua:
            print("BERHENTI: belum ada user. Jalankan `python seed.py` lebih dulu.")
            return 1

        members = _pastikan_member(rng)
        _pastikan_harga_bahan(rng, admin)

        hari_mulai = (datetime.utcnow() - timedelta(days=days - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0)

        kategori_bahan = ExpenseCategory.query.filter(ExpenseCategory.name.like('%Bahan%')).first() \
            or ExpenseCategory.query.first()
        kategori_umum = ExpenseCategory.query.filter(~ExpenseCategory.name.like('%Bahan%')).first() \
            or ExpenseCategory.query.first()
        base, kopi = _siapkan_base_espresso()

        total_tx = 0
        total_omzet = 0
        batch_seduh = 0
        for n in range(days):
            tanggal = hari_mulai + timedelta(days=n)
            akhir_pekan = tanggal.weekday() >= 5

            # Urutan seperti di kedai: restok datang pagi, lalu menyeduh base,
            # baru buka kasir. Kalau dibalik, stok terlanjur minus sebelum
            # barangnya datang.
            pagi = min(tanggal.replace(hour=7), datetime.utcnow())
            _restok_bila_menipis(rng, admin, kategori_bahan, pagi)
            if rng.random() < 0.7 and _seduh_base_espresso(rng, base, kopi, pagi):
                batch_seduh += 1
            db.session.commit()

            # Tidak ada shift pagi/malam: sesi kas dibuka sesuai keramaian.
            jumlah_sesi = 2 if akhir_pekan else rng.choices([1, 2], weights=[60, 40])[0]
            urut_hari = 0

            for sesi in range(1, jumlah_sesi + 1):
                pembuka = rng.choice(kasir_semua)
                sekarang = datetime.utcnow()
                mulai = min(tanggal.replace(hour=8 if sesi == 1 else 15, minute=0), sekarang)
                selesai = min(tanggal.replace(
                    hour=15 if sesi == 1 and jumlah_sesi > 1 else 22, minute=0), sekarang)
                if selesai <= mulai:
                    continue    # sesi sore hari ini belum dibuka
                modal_awal = rng.choice([200000, 300000, 500000])

                shift = Shift(type=f"SESI {sesi}", sessionNo=sesi, startTime=mulai,
                              endTime=selesai, status='CLOSED', startingCash=modal_awal,
                              userId=pembuka.id, openedBy=pembuka.id, closedBy=pembuka.id,
                              currentUserId=pembuka.id, createdAt=mulai, updatedAt=selesai)
                db.session.add(shift)
                db.session.flush()

                banyak = rng.randrange(18, 34) if akhir_pekan else rng.randrange(9, 22)
                tunai_sesi = 0
                for _ in range(banyak):
                    waktu = _jam_acak(rng, tanggal)
                    if not (mulai <= waktu <= selesai):
                        waktu = mulai + timedelta(minutes=rng.randrange(
                            max(1, int((selesai - mulai).total_seconds() // 60))))
                    urut_hari += 1
                    tx = _buat_transaksi(rng, waktu, menus, members,
                                         rng.choice(kasir_semua), shift, urut_hari)
                    total_tx += 1
                    total_omzet += tx.totalAmount
                    if tx.paymentMethod == 'CASH':
                        tunai_sesi += tx.totalAmount

                shift.expectedEndingCash = modal_awal + tunai_sesi
                # Selisih kas kecil itu wajar; sesekali memang tidak pas.
                selisih = rng.choice([0, 0, 0, 0, -5000, 2000, -2000])
                shift.endingCash = shift.expectedEndingCash + selisih
                if selisih:
                    shift.status = 'NEEDS_REVIEW'
                    shift.closingNote = 'Selisih kas kecil, belum ditelusuri'
                db.session.commit()

            if kategori_umum and rng.random() < 0.4:
                nama, murah, mahal = rng.choice(PENGELUARAN_RUTIN)
                db.session.add(Expense(amount=rng.randrange(murah, mahal), date=tanggal,
                                       categoryId=kategori_umum.id, userId=admin.id,
                                       paymentSource='CASH_DRAWER', notes=nama))
        db.session.commit()

        # Beberapa transaksi dibatalkan, supaya alur void & pengembalian stok ikut terisi.
        semua = Transaction.query.filter_by(status='COMPLETED').all()
        for tx in rng.sample(semua, min(3, len(semua))):
            tx.status = 'VOID'
            tx.voidReason = rng.choice(['Salah input menu', 'Pelanggan batal', 'Salah metode bayar'])
            tx.voidedAt = tx.createdAt + timedelta(minutes=rng.randrange(5, 40))
            tx.voidedBy = admin.id
        db.session.commit()

        print(f"\n[Demo] Selesai untuk {days} hari terakhir (seed={seed})")
        print(f"[Demo] {total_tx} transaksi, omzet Rp {total_omzet:,}".replace(',', '.'))
        print(f"[Demo] {len(members)} member, {Shift.query.count()} sesi kas, "
              f"{batch_seduh} kali seduhan base")
        if base:
            print(f"[Demo] Base Espresso: sisa {base.stock:g} ml @ Rp {base.costPerUnit:.2f}/ml")
        minus = [i.name for i in InventoryItem.query.all() if (i.stock or 0) < 0]
        if minus:
            print(f"[Demo] Catatan: stok masih minus di {', '.join(minus)}")
        print("[Demo] Pasang 'Base Espresso' di resep menu kopi lewat halaman Menu "
              "untuk melihat HPP-nya ikut terhitung.")
        return 0


def undo_demo(app=None, yakin=False):
    """
    Kosongkan seluruh data transaksional.

    PENTING: skrip ini TIDAK bisa membedakan baris demo dari penjualan asli --
    waktu membuatnya tidak ada penanda yang dipasang. Jadi ini menghapus SEMUA
    transaksi, sesi kas, pengeluaran, dan mutasi stok, bukan cuma yang demo.
    Hanya pakai di database uji coba.

    Master data (menu, bahan, member, pengguna) tidak disentuh.
    """
    app = app or create_app()
    with app.app_context():
        jumlah = {
            'Rincian transaksi': TransactionItem.query.count(),
            'Transaksi': Transaction.query.count(),
            'Sesi kas': Shift.query.count(),
            'Pengeluaran': Expense.query.count(),
            'Mutasi stok': InventoryLog.query.count(),
        }
        if not any(jumlah.values()):
            print('Tidak ada data transaksional untuk dihapus.')
            return 0

        print('Akan DIHAPUS dari database ini:')
        for nama, n in jumlah.items():
            print(f"  {nama:20} {n:>7}")
        print('\nIni menghapus SEMUA baris di atas, termasuk penjualan asli kalau ada.')
        print('Master data (menu, bahan, member) tidak disentuh.')

        if not yakin:
            print('\nTidak ada yang dihapus. Ulangi dengan --undo --yes kalau memang yakin.')
            return 1

        # Urutan mengikuti kunci asing: anak lebih dulu, induk belakangan.
        TransactionItem.query.delete(synchronize_session=False)
        Transaction.query.delete(synchronize_session=False)
        Expense.query.delete(synchronize_session=False)
        InventoryLog.query.delete(synchronize_session=False)
        Shift.query.delete(synchronize_session=False)
        db.session.commit()

        print('\nData transaksional dikosongkan.')
        print('Catatan: angka stok bahan TIDAK ikut dikembalikan -- mutasinya sudah '
              'terlanjur diterapkan ke stok. Perbaiki lewat Opname atau Sesuaikan Stok.')
        return 0


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='Isi database dengan data pemakaian contoh.')
    p.add_argument('--undo', action='store_true',
                   help='kosongkan SEMUA data transaksional (hanya untuk database uji coba)')
    p.add_argument('--yes', action='store_true', help='lanjutkan penghapusan tanpa bertanya lagi')
    p.add_argument('--days', type=int, default=14, help='rentang hari ke belakang (default 14)')
    p.add_argument('--seed', type=int, default=42,
                   help='benih angka acak; benih sama pada database yang sama-sama kosong '
                        'menghasilkan data yang sama')
    p.add_argument('--force', action='store_true', help='jalan walau sudah ada transaksi')
    a = p.parse_args()
    if a.undo:
        sys.exit(undo_demo(yakin=a.yes))
    sys.exit(seed_demo(a.days, a.seed, a.force))
