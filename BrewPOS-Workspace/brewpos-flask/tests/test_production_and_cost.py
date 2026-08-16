"""
Harga beli menyusul + produksi bahan setengah jadi.

Dua hal yang diuji di sini:

1. Bahan boleh dicatat lebih dulu tanpa harga, lalu harganya diisi belakangan.
   Form Edit Bahan sempat mengirim costPerUnit tanpa pernah dibaca API, jadi
   harga terlihat tersimpan padahal hilang -- dan HPP menu ikut tertinggal.

2. Produksi batch: 60 g bubuk kopi diseduh mokapot jadi 300 ml Base Espresso.
   Barista tidak perlu menebak gram per cup; cukup ukur sekali per batch.
"""
from app.extensions import db
from app.models.category import Category
from app.models.inventory import InventoryItem, InventoryLog
from app.models.menu import Menu, RecipeIngredient


def _base_item():
    item = InventoryItem(name='Base Espresso', unit='ml', stock=0.0, minStock=50.0)
    db.session.add(item)
    db.session.commit()
    return item


def _menu_from_base(base, ml_per_cup=30.0):
    cat = Category.query.first()
    m = Menu(name='Es Kopi Susu', price=22000, hpp=0, categoryId=cat.id)
    db.session.add(m)
    db.session.flush()
    db.session.add(RecipeIngredient(menuId=m.id, inventoryItemId=base.id, quantityNeeded=ml_per_cup))
    db.session.commit()
    return m


# --- 1. Harga menyusul ------------------------------------------------------

def test_bahan_bisa_dibuat_tanpa_harga(client, admin_headers):
    res = client.post('/api/inventory', headers=admin_headers, json={'name': 'Susu UHT', 'unit': 'ml', 'stock': 2000})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['costPerUnit'] == 0.0


def test_harga_bisa_diisi_saat_membuat(client, admin_headers):
    res = client.post('/api/inventory', headers=admin_headers, json={'name': 'Gula Aren', 'unit': 'ml', 'costPerUnit': 35.0})
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['costPerUnit'] == 35.0


def test_harga_menyusul_tersimpan_dan_hpp_ikut_terkoreksi(client, app, bean, menu, admin_headers):
    """Bekas bug: PUT membuang costPerUnit diam-diam, HPP menu tidak pernah berubah."""
    assert menu.hpp == 6000  # nilai lama dari fixture, belum mengikuti resep

    res = client.put(f'/api/inventory/{bean.id}', headers=admin_headers, json={'costPerUnit': 250.0})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['costPerUnit'] == 250.0

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).costPerUnit == 250.0
    # resep fixture: 18 g per cup -> 18 * 250
    assert Menu.query.get(menu.id).hpp == 4500


def test_harga_negatif_ditolak(client, bean, admin_headers):
    res = client.put(f'/api/inventory/{bean.id}', headers=admin_headers, json={'costPerUnit': -1})
    assert res.status_code == 400


def test_edit_tanpa_menyebut_harga_tidak_menghapus_harga(client, bean, admin_headers):
    res = client.put(f'/api/inventory/{bean.id}', headers=admin_headers, json={'minStock': 55})
    assert res.status_code == 200
    assert res.get_json()['costPerUnit'] == 200.0


def test_pembelian_mundur_memundurkan_stok_dan_pengeluaran_sekaligus(client, app, bean, admin_headers):
    """
    Toko sudah berjualan sebelum aplikasi ini ada, jadi nota lama diinput mundur.
    Tanggal pembelian sempat hanya dipakai baris Pengeluaran sementara mutasi
    stoknya bertanggal hari ini -- satu nota muncul di dua tanggal berbeda dan
    riwayat stok tidak bisa dicocokkan dengan notanya.
    """
    from app.models.expense import Expense, ExpenseCategory
    db.session.add(ExpenseCategory(name='Bahan Baku'))
    db.session.commit()

    res = client.post('/api/inventory/purchase', headers=admin_headers, json={
        'itemId': bean.id, 'quantity': 1000, 'totalCost': 250000,
        'date': '2026-07-15T09:30:00', 'supplier': 'CV Kopi Nusantara'})
    assert res.status_code == 201, res.get_json()

    log = InventoryLog.query.filter_by(itemId=bean.id, type='IN').order_by(
        InventoryLog.id.desc()).first()
    assert log.createdAt.date().isoformat() == '2026-07-15'

    exp = Expense.query.order_by(Expense.id.desc()).first()
    assert exp.date.date().isoformat() == '2026-07-15'
    # Dua-duanya harus jatuh di tanggal yang sama, itu inti perbaikannya.
    assert log.createdAt.date() == exp.date.date()


def test_pembelian_tanpa_tanggal_tetap_jalan(client, app, bean, admin_headers):
    res = client.post('/api/inventory/purchase', headers=admin_headers, json={
        'itemId': bean.id, 'quantity': 500, 'totalCost': 100000})
    assert res.status_code == 201, res.get_json()


def test_tanggal_ngawur_tidak_menggagalkan_pembelian(client, app, bean, admin_headers):
    """Nota tetap harus tercatat; tanggal yang tidak terbaca jatuh ke hari ini."""
    res = client.post('/api/inventory/purchase', headers=admin_headers, json={
        'itemId': bean.id, 'quantity': 500, 'totalCost': 100000, 'date': 'kemarin sore'})
    assert res.status_code == 201, res.get_json()


# --- 2. Produksi ------------------------------------------------------------

def test_produksi_memindahkan_stok_dan_menurunkan_harga_per_ml(client, app, bean, admin_headers):
    base = _base_item()

    res = client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': 60}],
        'notes': 'Seduh mokapot pagi'
    })
    assert res.status_code == 201, res.get_json()
    body = res.get_json()

    # 60 g x Rp 200 = Rp 12.000 untuk 300 ml -> Rp 40 per ml
    assert body['totalCost'] == 12000.0
    assert body['batchCostPerUnit'] == 40.0
    assert body['warnings'] == []

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).stock == 940.0
    hasil = InventoryItem.query.get(base.id)
    assert hasil.stock == 300.0
    assert hasil.costPerUnit == 40.0


def test_harga_hasil_pakai_rata_rata_tertimbang(client, app, bean, admin_headers):
    """Sisa base kemarin ikut dihitung, jadi nilai stok tidak melompat."""
    base = _base_item()
    client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': 60}]})

    # Kopi naik harga, seduhan berikutnya lebih mahal
    client.put(f'/api/inventory/{bean.id}', headers=admin_headers, json={'costPerUnit': 300.0})
    res = client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': 60}]})
    assert res.status_code == 201, res.get_json()

    # batch kedua Rp 60/ml, tapi rata-rata 600 ml = (12.000 + 18.000) / 600
    assert res.get_json()['batchCostPerUnit'] == 60.0
    db.session.expire_all()
    assert InventoryItem.query.get(base.id).costPerUnit == 50.0


def test_produksi_memperbarui_hpp_menu_yang_memakai_hasil(client, app, bean, admin_headers):
    base = _base_item()
    m = _menu_from_base(base, ml_per_cup=30.0)

    client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': 60}]})

    db.session.expire_all()
    assert Menu.query.get(m.id).hpp == 1200  # 30 ml x Rp 40


def test_produksi_mencatat_jejak_keluar_masuk(client, app, bean, admin_headers):
    base = _base_item()
    client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': 60}]})

    keluar = InventoryLog.query.filter_by(itemId=bean.id, type='OUT').first()
    masuk = InventoryLog.query.filter_by(itemId=base.id, type='IN').first()
    assert keluar is not None and masuk is not None
    # Bekas kelemahan log otomatis: biayanya selalu 0 sehingga tidak bisa ditelusuri
    assert keluar.totalCost == 12000.0 and keluar.costPerUnit == 200.0
    assert masuk.totalCost == 12000.0 and masuk.costPerUnit == 40.0


def test_produksi_menolak_hasil_dipakai_sebagai_bahan(client, app, bean, admin_headers):
    base = _base_item()
    res = client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': base.id, 'quantity': 60}]})
    assert res.status_code == 400


def test_produksi_menolak_jumlah_tidak_masuk_akal(client, app, bean, admin_headers):
    base = _base_item()
    assert client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 0,
        'inputs': [{'itemId': bean.id, 'quantity': 60}]}).status_code == 400
    assert client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300, 'inputs': []}).status_code == 400
    assert client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': -5}]}).status_code == 400


def test_bahan_bermasalah_tidak_menyisakan_potongan_setengah_jalan(client, app, bean, admin_headers):
    """Baris kedua tidak sah -> stok baris pertama tidak boleh terlanjur terpotong."""
    base = _base_item()
    res = client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': bean.id, 'quantity': 60}, {'itemId': 999999, 'quantity': 10}]})
    assert res.status_code == 404

    db.session.expire_all()
    assert InventoryItem.query.get(bean.id).stock == 1000.0
    assert InventoryItem.query.get(base.id).stock == 0.0


def test_produksi_memperingatkan_bahan_tanpa_harga_dan_stok_minus(client, app, admin_headers):
    tanpa_harga = InventoryItem(name='Bubuk Kopi Belum Dihargai', unit='g', stock=10.0)
    db.session.add(tanpa_harga)
    db.session.commit()
    base = _base_item()

    res = client.post('/api/inventory/production', headers=admin_headers, json={
        'outputItemId': base.id, 'outputQty': 300,
        'inputs': [{'itemId': tanpa_harga.id, 'quantity': 60}]})
    assert res.status_code == 201, res.get_json()

    peringatan = ' | '.join(res.get_json()['warnings'])
    assert 'minus' in peringatan
    assert 'harga beli' in peringatan
