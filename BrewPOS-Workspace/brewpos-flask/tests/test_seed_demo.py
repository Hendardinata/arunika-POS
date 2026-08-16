"""
seed_demo.py dijalankan ke database sekali pakai, bukan database sungguhan.

Yang dijaga di sini bukan angkanya (memang acak), tapi bahwa data yang lahir
masuk akal: transaksi punya item, stok bahan ikut terpotong, sesi kas nyambung
dengan transaksinya, dan pengaman anti-timpa benar-benar menahan.
"""
from datetime import datetime

from app.extensions import db
from app.models.customer import Customer
from app.models.expense import ExpenseCategory
from app.models.inventory import InventoryItem, InventoryLog
from app.models.shift import Shift
from app.models.category import Category
from app.models.menu import Menu, RecipeIngredient
from app.models.transaction import Transaction, TransactionItem
from seed_demo import seed_demo, undo_demo


def _perbanyak_menu():
    """
    Fixture bawaan cuma punya satu menu dengan satu bahan. Konsumsinya terlalu
    ringan sehingga penjaga stok minus tidak pernah menggigit -- padahal di
    pemakaian nyata justru di situ masalahnya muncul.
    """
    if Menu.query.count() > 1:
        return
    kategori = Category.query.first()
    kopi = InventoryItem.query.filter_by(name='Biji Kopi Arabica').first()
    cup = InventoryItem(name='Cup 16oz', unit='pcs', stock=200.0, minStock=50.0)
    susu = InventoryItem(name='Susu Fresh Milk', unit='ml', stock=3000.0, minStock=500.0)
    db.session.add_all([cup, susu])
    db.session.flush()

    for nama, harga in [('Americano', 18000), ('Cappuccino', 25000), ('Latte', 24000)]:
        m = Menu(name=nama, price=harga, hpp=0, categoryId=kategori.id)
        db.session.add(m)
        db.session.flush()
        db.session.add(RecipeIngredient(menuId=m.id, inventoryItemId=kopi.id, quantityNeeded=18.0))
        db.session.add(RecipeIngredient(menuId=m.id, inventoryItemId=cup.id, quantityNeeded=1.0))
        db.session.add(RecipeIngredient(menuId=m.id, inventoryItemId=susu.id, quantityNeeded=120.0))
    db.session.commit()


def _jalankan(app, **kw):
    # Kategori pengeluaran hanya ada di seed.py, sementara fixture tes tidak
    # memuatnya. Tanpa ini bagian pembelian bahan diam-diam terlewat.
    if not ExpenseCategory.query.first():
        db.session.add(ExpenseCategory(name='Bahan Baku'))
        db.session.add(ExpenseCategory(name='Operasional'))
        db.session.commit()
    _perbanyak_menu()
    opsi = {'days': 5, 'seed': 1, 'force': False, 'app': app}
    opsi.update(kw)
    return seed_demo(**opsi)


def test_menghasilkan_transaksi_yang_utuh(app):
    assert _jalankan(app) == 0

    transaksi = Transaction.query.all()
    assert transaksi, 'tidak ada transaksi yang dibuat'

    for tx in transaksi:
        assert tx.items, f'transaksi {tx.id} tanpa item'
        assert tx.totalAmount == tx.subTotal - (tx.discountAmount or 0)
        assert tx.totalAmount >= 0
        assert tx.customerId and tx.shiftId and tx.userId
        assert tx.transactionCode and tx.transactionCode.startswith('TR')


def test_harga_baris_ikut_harga_menu_dan_hpp_tersimpan(app):
    _jalankan(app)
    for item in TransactionItem.query.all():
        assert item.quantity > 0
        assert item.price == item.menu.price
        # hpp adalah cuplikan modal saat terjual -- dipakai laporan margin.
        assert item.hpp == (item.menu.hpp or 0)


def test_stok_bahan_ikut_terpotong(app, bean):
    stok_awal = bean.stock
    _jalankan(app)

    db.session.expire_all()
    keluar = InventoryLog.query.filter_by(itemId=bean.id, type='OUT').count()
    assert keluar > 0, 'penjualan tidak memotong stok bahan sama sekali'
    assert InventoryItem.query.get(bean.id).stock != stok_awal


def test_sesi_kas_nyambung_dengan_transaksinya(app):
    _jalankan(app)

    for shift in Shift.query.all():
        assert shift.sessionNo and shift.type.startswith('SESI')  # bukan MORNING/NIGHT
        assert shift.startTime and shift.endTime
        tunai = sum(t.totalAmount for t in shift.transactions
                    if t.paymentMethod == 'CASH' and t.status == 'COMPLETED')
        # Transaksi yang di-void tidak dikembalikan kasnya di data demo, jadi
        # cocokkan hanya bila sesi ini tidak punya void.
        if all(t.status == 'COMPLETED' for t in shift.transactions):
            assert shift.expectedEndingCash == shift.startingCash + tunai


def test_member_pakai_hp_atau_email_bukan_wajib_keduanya(app):
    _jalankan(app)
    members = Customer.query.all()
    assert members
    for m in members:
        assert m.phone or m.email, f'member {m.nickname} tanpa identitas sama sekali'
    assert any(m.phone and not m.email for m in members)
    assert any(m.email and not m.phone for m in members)


def test_base_espresso_terbentuk_dengan_harga_masuk_akal(app):
    _jalankan(app, days=30)
    base = InventoryItem.query.filter_by(name='Base Espresso').first()
    assert base is not None
    assert base.unit == 'ml'
    if base.stock > 0:
        # Harga per ml harus turun jauh dari harga per gram kopinya.
        assert 0 < base.costPerUnit < 500


def test_semua_bahan_punya_harga_setelah_seed(app):
    """Bahan berharga nol bikin HPP nol dan margin terlihat 100%."""
    _jalankan(app)
    for item in InventoryItem.query.filter(InventoryItem.isActive == True).all():  # noqa: E712
        assert (item.costPerUnit or 0) > 0, f'{item.name} masih tanpa harga'


def test_stok_tidak_terjun_ke_minus_karena_lupa_restok(app):
    """
    Penjualan menggerus stok tiap hari. Sempat semua bahan berakhir minus ribuan
    gram -- data yang terlihat rusak dan tidak bisa dipakai memperagakan
    peringatan stok menipis. Restok harian yang menahannya.
    """
    _jalankan(app, days=21)
    for item in InventoryItem.query.filter(InventoryItem.isActive == True).all():  # noqa: E712
        assert (item.stock or 0) >= 0, \
            f'{item.name} berakhir minus ({item.stock:g} {item.unit}), restok tidak jalan'


def test_mutasi_stok_sewaktu_dengan_transaksinya(app):
    """
    deduct_ingredients_for_order memakai createdAt bawaan (waktu sekarang),
    padahal transaksi demo bertanggal mundur. Sempat seluruh potongan stok
    menumpuk di satu detik yang sama sehingga riwayat inventori tidak terbaca
    dan hitungan pemakaian harian jadi berlipat.
    """
    _jalankan(app, days=10)
    potongan = InventoryLog.query.filter(InventoryLog.notes.like('Auto Deduct%')).all()
    assert potongan, 'penjualan tidak memotong stok sama sekali'

    hari = {log.createdAt.date() for log in potongan}
    assert len(hari) > 1, 'semua potongan stok bertanggal di hari yang sama'


def test_restok_tercatat_sebagai_pembelian_dan_pengeluaran(app):
    _jalankan(app, days=21)
    restok = InventoryLog.query.filter(InventoryLog.notes.like('Restok%')).all()
    assert restok, 'tidak ada restok sama sekali'
    for log in restok:
        assert log.type == 'IN'
        assert log.totalCost > 0 and log.costPerUnit > 0
        assert log.supplier


def test_ada_transaksi_yang_dibatalkan(app):
    _jalankan(app)
    void = Transaction.query.filter_by(status='VOID').all()
    assert void, 'tidak ada contoh transaksi batal'
    for tx in void:
        assert tx.voidReason and tx.voidedAt and tx.voidedBy


def test_menolak_menimpa_database_yang_sudah_ada_transaksinya(app):
    assert _jalankan(app) == 0
    sebelum = Transaction.query.count()

    # Jalan kedua tanpa --force harus berhenti dan tidak menambah apa pun.
    assert _jalankan(app, seed=2) == 1
    assert Transaction.query.count() == sebelum

    assert _jalankan(app, seed=2, force=True) == 0
    assert Transaction.query.count() > sebelum


def test_undo_tanpa_yes_tidak_menghapus_apa_apa(app):
    """Penghapusan menyeluruh tidak boleh terjadi hanya karena salah ketik perintah."""
    _jalankan(app)
    sebelum = Transaction.query.count()
    assert sebelum > 0

    assert undo_demo(app=app, yakin=False) == 1
    assert Transaction.query.count() == sebelum


def test_undo_mengosongkan_data_transaksional(app):
    _jalankan(app)
    assert Transaction.query.count() > 0

    assert undo_demo(app=app, yakin=True) == 0
    assert Transaction.query.count() == 0
    assert TransactionItem.query.count() == 0
    assert Shift.query.count() == 0
    assert InventoryLog.query.count() == 0


def test_undo_tidak_menyentuh_master_data(app):
    """Menu, bahan, dan member harus selamat -- itu bukan data demo."""
    _jalankan(app)
    menu_sebelum = Menu.query.count()
    bahan_sebelum = InventoryItem.query.count()
    member_sebelum = Customer.query.count()

    undo_demo(app=app, yakin=True)

    assert Menu.query.count() == menu_sebelum
    assert InventoryItem.query.count() == bahan_sebelum
    assert Customer.query.count() == member_sebelum


def test_undo_di_database_kosong_aman(app):
    assert undo_demo(app=app, yakin=True) == 0


def test_bisa_seed_ulang_setelah_undo(app):
    _jalankan(app)
    undo_demo(app=app, yakin=True)
    # Tanpa transaksi tersisa, pengaman anti-timpa harus mengizinkan lagi.
    assert _jalankan(app, seed=5) == 0
    assert Transaction.query.count() > 0


def test_tidak_ada_transaksi_di_masa_depan(app):
    _jalankan(app)
    sekarang = datetime.utcnow()
    for tx in Transaction.query.all():
        assert tx.createdAt <= sekarang, 'ada transaksi bertanggal di masa depan'
