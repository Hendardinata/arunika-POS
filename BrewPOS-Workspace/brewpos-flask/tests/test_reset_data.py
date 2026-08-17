"""
reset_data.py dijalankan ke database sekali pakai, bukan database sungguhan.

Skrip penghapus harus dibuktikan dua arah: menghapus yang seharusnya hilang,
DAN menyisakan yang seharusnya bertahan. Yang kedua justru lebih penting --
salah satu baris master ikut terhapus berarti mengetik ulang seluruh menu.
"""
from datetime import datetime

import pytest

from app.extensions import db
from app.models.category import Category
from app.models.customer import Customer
from app.models.expense import Expense, ExpenseCategory
from app.models.inventory import InventoryItem, InventoryLog
from app.models.menu import Menu, RecipeIngredient
from app.models.reward import Reward
from app.models.shift import Shift
from app.models.system_settings import SystemSettings
from app.models.transaction import Transaction, TransactionItem
from app.models.user import User
from reset_data import reset_data


@pytest.fixture
def isi_data(app, menu, bean):
    """Data operasional secukupnya, plus member Rifqi yang harus selamat."""
    admin = User.query.filter_by(role='SUPERADMIN').first()
    rifqi = Customer(nickname='Rifqi', points=120, xp=120, level=2, streakCount=3)
    lain = Customer(nickname='Budi', points=10, xp=10, level=1, streakCount=0)
    kat = ExpenseCategory(name='Operasional')
    db.session.add_all([rifqi, lain, kat])
    db.session.flush()

    s = Shift(type='SESI 1', sessionNo=1, startTime=datetime.utcnow(), status='OPEN',
              startingCash=200000, userId=admin.id, openedBy=admin.id)
    db.session.add(s)
    db.session.flush()

    tx = Transaction(subTotal=25000, totalAmount=25000, taxAmount=0, status='COMPLETED',
                     customerId=rifqi.id, shiftId=s.id, userId=admin.id,
                     transactionCode='TR20260810000001')
    db.session.add(tx)
    db.session.flush()
    db.session.add(TransactionItem(transactionId=tx.id, menuId=menu.id, quantity=1,
                                   price=25000, hpp=6000))
    db.session.add(Expense(amount=50000, date=datetime.utcnow(), categoryId=kat.id,
                           userId=admin.id, notes='uji'))
    db.session.add(InventoryLog(itemId=bean.id, quantity=100, type='IN',
                                costPerUnit=200, totalCost=20000, notes='uji'))
    db.session.commit()
    return {'rifqi': rifqi.id, 'lain': lain.id}


def test_bawaan_hanya_menampilkan_tidak_menghapus(app, isi_data):
    """Tanpa --yes tidak boleh ada satu baris pun yang hilang."""
    assert reset_data(['Rifqi'], yakin=False, app=app) == 1
    assert Transaction.query.count() == 1
    assert Customer.query.count() == 2


def test_data_operasional_terhapus(app, isi_data):
    assert reset_data(['Rifqi'], yakin=True, app=app) == 0

    assert Transaction.query.count() == 0
    assert TransactionItem.query.count() == 0
    assert Shift.query.count() == 0
    assert Expense.query.count() == 0
    assert InventoryLog.query.count() == 0


def test_master_data_tidak_ikut_terhapus(app, isi_data):
    """Salah satu ini ikut terhapus = mengetik ulang seluruh menu."""
    sebelum = (Menu.query.count(), Category.query.count(), RecipeIngredient.query.count(),
               InventoryItem.query.count(), Reward.query.count(),
               ExpenseCategory.query.count(), SystemSettings.query.count(),
               User.query.count())
    reset_data(['Rifqi'], yakin=True, app=app)
    sesudah = (Menu.query.count(), Category.query.count(), RecipeIngredient.query.count(),
               InventoryItem.query.count(), Reward.query.count(),
               ExpenseCategory.query.count(), SystemSettings.query.count(),
               User.query.count())
    assert sebelum == sesudah


def test_member_yang_disebut_bertahan_sisanya_hilang(app, isi_data):
    reset_data(['Rifqi'], yakin=True, app=app)

    tersisa = Customer.query.all()
    assert [c.nickname for c in tersisa] == ['Rifqi']
    # Poin & levelnya tidak ikut direset -- yang diminta hanya menghapus data lain
    assert tersisa[0].points == 120 and tersisa[0].level == 2


def test_stok_dan_harga_bahan_dinolkan_tapi_barisnya_tetap(app, isi_data, bean):
    jumlah_bahan = InventoryItem.query.count()
    assert bean.stock > 0

    reset_data(['Rifqi'], yakin=True, app=app)

    db.session.expire_all()
    assert InventoryItem.query.count() == jumlah_bahan
    for item in InventoryItem.query.all():
        assert item.stock == 0.0, f'{item.name} stoknya belum nol'
        assert item.costPerUnit == 0.0, f'{item.name} harganya belum nol'


def test_nama_member_tidak_peduli_besar_kecil_huruf(app, isi_data):
    assert reset_data(['rifqi'], yakin=True, app=app) == 0
    assert [c.nickname for c in Customer.query.all()] == ['Rifqi']


def test_nama_member_salah_ketik_membatalkan_semuanya(app, isi_data):
    """
    Kalau diteruskan, member yang mau diselamatkan justru ikut terhapus --
    persis kebalikan dari maksud perintahnya.
    """
    assert reset_data(['Rifqii'], yakin=True, app=app) == 1
    assert Transaction.query.count() == 1
    assert Customer.query.count() == 2


def test_bisa_menyimpan_lebih_dari_satu_member(app, isi_data):
    reset_data(['Rifqi', 'Budi'], yakin=True, app=app)
    assert sorted(c.nickname for c in Customer.query.all()) == ['Budi', 'Rifqi']


def test_database_yang_sudah_kosong_aman(app):
    assert reset_data(['Rifqi'], yakin=True, app=app) == 0
