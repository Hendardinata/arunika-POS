from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models.menu import Menu, RecipeIngredient
from app.models.inventory import InventoryItem
from app.middleware.auth import get_current_user_id
from app.services.system_logger import log_activity

recipe_bp = Blueprint('recipe', __name__, url_prefix='/api/recipes')


def _hpp_dari_resep(menu):
    """HPP satu porsi menurut resep dan harga bahan yang berlaku SEKARANG.

    menu.hpp adalah angka beku: nilainya baru berubah kalau resep disimpan
    ulang atau ada pembelian bahan. Fungsi ini yang dipakai halaman /hpp untuk
    menunjukkan selisihnya terhadap harga bahan hari ini.

    Kembalian: (total, jumlah_bahan, nama_bahan_yang_belum_ada_harganya)
    """
    total = 0.0
    tanpa_harga = []
    for ri in menu.recipeIngredients:
        inv = ri.inventoryItem
        harga = (inv.costPerUnit or 0.0) if inv else 0.0
        total += (ri.quantityNeeded or 0.0) * harga
        if harga <= 0:
            tanpa_harga.append(inv.name if inv else 'Bahan')
    return total, len(menu.recipeIngredients), tanpa_harga


def _menu_dengan_resep():
    return Menu.query.options(
        joinedload(Menu.recipeIngredients).joinedload(RecipeIngredient.inventoryItem),
        joinedload(Menu.category),
    )


@recipe_bp.route('', methods=['GET'])
def get_recipes():
    try:
        menus = Menu.query.all()
        return jsonify([m.to_dict(include_category=True) for m in menus])
    except Exception as e:
        return jsonify({'error': 'Internal Server Error', 'details': str(e)}), 500


@recipe_bp.route('/menu/<int:menu_id>', methods=['GET'])
def get_menu_recipe(menu_id):
    """
    Returns recipe ingredients for a menu with real-time unit costs, sub-costs, and total calculated HPP.
    """
    try:
        menu = Menu.query.get(menu_id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        ingredients = []
        total_calculated_hpp = 0.0

        for ri in menu.recipeIngredients:
            inv = ri.inventoryItem
            unit_cost = (inv.costPerUnit or 0.0) if inv else 0.0
            sub_cost = round(ri.quantityNeeded * unit_cost, 2)
            total_calculated_hpp += sub_cost

            ingredients.append({
                'id': ri.id,
                'inventoryItemId': ri.inventoryItemId,
                'name': inv.name if inv else 'Bahan',
                'unit': inv.unit if inv else 'pcs',
                'quantityNeeded': ri.quantityNeeded,
                'costPerUnit': unit_cost,
                'subCost': sub_cost
            })

        return jsonify({
            'menuId': menu.id,
            'menuName': menu.name,
            'price': menu.price,
            'currentHpp': menu.hpp,
            'recipeNotes': menu.recipeNotes or '',
            'calculatedHpp': int(round(total_calculated_hpp)),
            'ingredients': ingredients
        })
    except Exception as e:
        return jsonify({'error': 'Failed to fetch menu recipe', 'details': str(e)}), 500


@recipe_bp.route('/menu/<int:menu_id>', methods=['POST', 'PUT'])
def save_menu_recipe(menu_id):
    """
    Saves recipe ingredients, updates notes, auto-calculates total HPP, and updates menu.hpp.
    """
    data = request.get_json() or {}
    ingredients_data = data.get('ingredients', [])
    recipe_notes = data.get('recipeNotes')
    apply_hpp = data.get('applyHpp', True)

    try:
        menu = Menu.query.get(menu_id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        if recipe_notes is not None:
            menu.recipeNotes = recipe_notes

        # Clear existing recipe ingredients
        RecipeIngredient.query.filter_by(menuId=menu.id).delete()

        total_calculated_hpp = 0.0

        for it in ingredients_data:
            inv_id = int(it.get('inventoryItemId'))
            qty_needed = float(it.get('quantityNeeded', 0))

            if qty_needed > 0:
                ri = RecipeIngredient(
                    menuId=menu.id,
                    inventoryItemId=inv_id,
                    quantityNeeded=qty_needed
                )
                db.session.add(ri)

                inv = InventoryItem.query.get(inv_id)
                unit_cost = (inv.costPerUnit or 0.0) if inv else 0.0
                total_calculated_hpp += (qty_needed * unit_cost)

        calc_hpp_int = int(round(total_calculated_hpp))
        if apply_hpp and calc_hpp_int > 0:
            menu.hpp = calc_hpp_int

        db.session.commit()

        return jsonify({
            'message': 'Resep berhasil disimpan dan HPP otomatis diperbarui!',
            'menuId': menu.id,
            'hpp': menu.hpp,
            'calculatedHpp': calc_hpp_int
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to save menu recipe', 'details': str(e)}), 500


@recipe_bp.route('/<int:menu_id>', methods=['POST'])
def update_recipe_notes(menu_id):
    data = request.get_json() or {}
    recipe_notes = data.get('recipeNotes')

    try:
        menu = Menu.query.get(menu_id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        menu.recipeNotes = recipe_notes
        db.session.commit()
        return jsonify({'message': 'Recipe updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal Server Error'}), 500


@recipe_bp.route('/hpp-overview', methods=['GET'])
def hpp_overview():
    """Semua menu: HPP tersimpan vs HPP resep dengan harga bahan terkini."""
    try:
        menus = _menu_dengan_resep().order_by(Menu.name.asc()).all()

        hasil = []
        for m in menus:
            total, jumlah_bahan, tanpa_harga = _hpp_dari_resep(m)
            hasil.append({
                'id': m.id,
                'code': m.get_code(),
                'name': m.name,
                'category': m.category.name if m.category else None,
                'price': m.price or 0,
                'isActive': bool(m.isActive) if m.isActive is not None else True,
                'storedHpp': m.hpp or 0,
                'recipeHpp': int(round(total)),
                'ingredientCount': jumlah_bahan,
                'missingCostItems': tanpa_harga,
            })

        return jsonify(hasil)
    except Exception as e:
        return jsonify({'error': 'Failed to build HPP overview', 'details': str(e)}), 500


@recipe_bp.route('/hpp-sync', methods=['POST'])
def hpp_sync():
    """Terapkan HPP hasil resep ke menu. Tanpa menuIds berarti semua menu.

    Menu tanpa resep -- atau yang seluruh bahannya belum berharga -- dilewati,
    bukan disetel 0. HPP 0 membuat laporan margin seolah untung 100%.
    """
    data = request.get_json(silent=True) or {}
    menu_ids = data.get('menuIds')

    q = _menu_dengan_resep()
    if menu_ids is not None:
        ids = [int(i) for i in menu_ids if str(i).strip().lstrip('-').isdigit()]
        if not ids:
            return jsonify({'error': 'menuIds tidak berisi id yang sah'}), 400
        q = q.filter(Menu.id.in_(ids))

    try:
        diperbarui = []
        dilewati = 0

        for m in q.all():
            total, jumlah_bahan, _ = _hpp_dari_resep(m)
            baru = int(round(total))
            if jumlah_bahan == 0 or baru <= 0:
                dilewati += 1
                continue
            if baru != (m.hpp or 0):
                diperbarui.append({
                    'menuId': m.id,
                    'name': m.name,
                    'from': m.hpp or 0,
                    'to': baru,
                })
                m.hpp = baru

        db.session.commit()

        if diperbarui:
            log_activity(
                'HPP_SYNC',
                user_id=get_current_user_id(),
                details=f"{len(diperbarui)} menu disamakan dengan HPP resep terkini",
                entity='Menu',
            )

        return jsonify({
            'message': f"{len(diperbarui)} menu diperbarui, {dilewati} dilewati (belum ada resep/harga bahan).",
            'updated': diperbarui,
            'skipped': dilewati,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to sync HPP', 'details': str(e)}), 500
