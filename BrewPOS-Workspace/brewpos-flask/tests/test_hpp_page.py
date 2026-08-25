"""
Halaman Perhitungan HPP: ringkasan selisih + tombol samakan.

menu.hpp adalah angka beku (baru berubah kalau resep disimpan ulang atau ada
pembelian bahan), jadi yang diuji di sini adalah dua hal yang membuat halaman
itu ada: selisihnya terhadap harga bahan hari ini terlihat, dan menyamakannya
tidak boleh menabrak menu yang belum punya resep -- HPP 0 membuat laporan
margin seolah untung 100%.
"""
from app.extensions import db
from app.models.category import Category
from app.models.inventory import InventoryItem
from app.models.menu import Menu, RecipeIngredient

# Fixture conftest: kopi 18 g/cup @ Rp 200/g -> HPP resep 3600, tapi menu.hpp = 6000
HPP_RESEP = 3600


def test_overview_menunjukkan_selisih_hpp_tersimpan_vs_resep(client, menu, admin_headers):
    res = client.get('/api/recipes/hpp-overview', headers=admin_headers)
    assert res.status_code == 200, res.get_json()

    baris = next(r for r in res.get_json() if r['id'] == menu.id)
    assert baris['storedHpp'] == 6000
    assert baris['recipeHpp'] == HPP_RESEP
    assert baris['ingredientCount'] == 1
    assert baris['missingCostItems'] == []


def test_bahan_tanpa_harga_ditandai(client, menu, admin_headers):
    susu = InventoryItem(name='Susu UHT', unit='ml', stock=1000.0, costPerUnit=0.0)
    db.session.add(susu)
    db.session.flush()
    db.session.add(RecipeIngredient(menuId=menu.id, inventoryItemId=susu.id, quantityNeeded=120.0))
    db.session.commit()

    res = client.get('/api/recipes/hpp-overview', headers=admin_headers)
    baris = next(r for r in res.get_json() if r['id'] == menu.id)
    assert baris['missingCostItems'] == ['Susu UHT']
    assert baris['recipeHpp'] == HPP_RESEP  # susu belum menambah biaya


def test_sync_menyamakan_hpp_menu_dengan_resep(client, menu, admin_headers):
    res = client.post('/api/recipes/hpp-sync', headers=admin_headers, json={'menuIds': [menu.id]})
    assert res.status_code == 200, res.get_json()

    body = res.get_json()
    assert body['updated'] == [{'menuId': menu.id, 'name': menu.name, 'from': 6000, 'to': HPP_RESEP}]

    db.session.expire_all()
    assert Menu.query.get(menu.id).hpp == HPP_RESEP


def test_sync_melewati_menu_tanpa_resep(client, admin_headers):
    """Menu tanpa resep tidak boleh disetel jadi HPP 0."""
    kosong = Menu(name='Air Mineral', price=5000, hpp=2000, categoryId=Category.query.first().id)
    db.session.add(kosong)
    db.session.commit()

    res = client.post('/api/recipes/hpp-sync', headers=admin_headers, json={'menuIds': [kosong.id]})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['skipped'] == 1

    db.session.expire_all()
    assert Menu.query.get(kosong.id).hpp == 2000


def test_sync_tanpa_menu_ids_mengenai_semua_menu(client, menu, admin_headers):
    res = client.post('/api/recipes/hpp-sync', headers=admin_headers, json={})
    assert res.status_code == 200, res.get_json()

    db.session.expire_all()
    assert Menu.query.get(menu.id).hpp == HPP_RESEP


def test_halaman_hpp_terdaftar_di_hak_akses(client, admin_headers):
    res = client.get('/api/role-access/allowed-routes', headers=admin_headers)
    assert res.status_code == 200
    assert '/hpp' in res.get_json()['allowedPaths']


def test_halaman_hpp_terender(client):
    res = client.get('/hpp')
    assert res.status_code == 200
    assert b'id="tabel-hpp"' in res.data
