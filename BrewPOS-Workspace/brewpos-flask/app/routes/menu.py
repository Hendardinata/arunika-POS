import os
import time
from flask import Blueprint, request, jsonify, current_app
from app.middleware.auth import get_current_user_id
from werkzeug.utils import secure_filename
from sqlalchemy import func
from app.extensions import db
from app.models.menu import Menu, RecipeIngredient
from app.models.transaction import TransactionItem
from app.models.inventory import InventoryItem
from app.services.system_logger import log_activity

menu_bp = Blueprint('menu', __name__, url_prefix='/api/menus')

def _save_upload_file(file):
    if not file or file.filename == '':
        return None
    filename = secure_filename(f"menu_{int(time.time()*1000)}_{file.filename}")
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)
    return f"/uploads/{filename}"

@menu_bp.route('', methods=['GET'])
def get_menus():
    try:
        # Sum quantity sold per menu
        sold_counts = db.session.query(
            TransactionItem.menuId,
            func.sum(TransactionItem.quantity).label('total_sold')
        ).group_by(TransactionItem.menuId).all()

        sold_map = {sc[0]: int(sc[1] or 0) for sc in sold_counts}

        # POS memanggil dengan activeOnly=1; halaman kelola menu tetap melihat
        # yang diarsipkan supaya bisa diaktifkan kembali.
        query = Menu.query
        if request.args.get('activeOnly') in ('1', 'true'):
            # MSSQL menolak "IS 1" yang dihasilkan is_(True); pakai perbandingan biasa.
            query = query.filter(Menu.isActive == True)  # noqa: E712

        menus = query.all()
        result = [m.to_dict(include_category=True, sold_count=sold_map.get(m.id, 0)) for m in menus]
        return jsonify(result)
    except Exception as e:
        print(f"Error fetching menus: {e}")
        return jsonify({'error': 'Failed to fetch menus', 'details': str(e)}), 500


@menu_bp.route('', methods=['POST'])
def create_menu():
    try:
        # Support both multipart form data and json
        if request.is_json:
            data = request.get_json() or {}
            name = data.get('name')
            description = data.get('description')
            price = int(data.get('price', 0))
            hpp = int(data.get('hpp', 0))
            category_id = int(data.get('categoryId', 0))
            image_url = data.get('imageUrl')
        else:
            name = request.form.get('name')
            description = request.form.get('description')
            price = int(request.form.get('price', 0))
            hpp = int(request.form.get('hpp', 0))
            category_id = int(request.form.get('categoryId', 0))
            image_url = request.form.get('imageUrl')
            
            if 'image' in request.files:
                uploaded_url = _save_upload_file(request.files['image'])
                if uploaded_url:
                    image_url = uploaded_url

        if not name or not price or not category_id:
            return jsonify({'error': 'Name, price, and categoryId are required'}), 400

        menu = Menu(
            name=name,
            description=description,
            price=price,
            hpp=hpp,
            categoryId=category_id,
            imageUrl=image_url
        )
        db.session.add(menu)
        db.session.commit()

        user_id = get_current_user_id()
        log_activity('CREATE_MENU', int(user_id) if user_id else None,
                     f"Created menu: {name}", 'Menu', menu.id)

        return jsonify(menu.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error creating menu: {e}")
        return jsonify({'error': 'Failed to create menu', 'details': str(e)}), 500


@menu_bp.route('/<int:id>', methods=['PUT'])
def update_menu(id):
    try:
        menu = Menu.query.get(id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        if request.is_json:
            data = request.get_json() or {}
            if 'name' in data: menu.name = data['name']
            if 'description' in data: menu.description = data['description']
            if 'price' in data: menu.price = int(data['price'])
            if 'hpp' in data: menu.hpp = int(data['hpp'])
            if 'categoryId' in data: menu.categoryId = int(data['categoryId'])
            if 'imageUrl' in data: menu.imageUrl = data['imageUrl']
            if 'isActive' in data: menu.isActive = bool(data['isActive'])
        else:
            if 'name' in request.form: menu.name = request.form['name']
            if 'description' in request.form: menu.description = request.form['description']
            if 'price' in request.form: menu.price = int(request.form['price'])
            if 'hpp' in request.form: menu.hpp = int(request.form['hpp'])
            if 'categoryId' in request.form: menu.categoryId = int(request.form['categoryId'])
            if 'imageUrl' in request.form: menu.imageUrl = request.form['imageUrl']

            if 'image' in request.files:
                uploaded_url = _save_upload_file(request.files['image'])
                if uploaded_url:
                    menu.imageUrl = uploaded_url

        db.session.commit()

        user_id = get_current_user_id()
        log_activity('UPDATE_MENU', int(user_id) if user_id else None,
                     f"Updated menu: {menu.name}", 'Menu', menu.id)

        return jsonify(menu.to_dict())
    except Exception as e:
        db.session.rollback()
        print(f"Error updating menu: {e}")
        return jsonify({'error': 'Failed to update menu', 'details': str(e)}), 500


@menu_bp.route('/<int:id>', methods=['DELETE'])
def delete_menu(id):
    try:
        menu = Menu.query.get(id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        # Check if used in transactions
        used_count = TransactionItem.query.filter_by(menuId=id).count()
        if used_count > 0:
            return jsonify({
                'error': f'Menu "{menu.name}" sudah terpakai di {used_count} transaksi, '
                         'jadi tidak bisa dihapus tanpa merusak riwayat penjualan. '
                         'Nonaktifkan saja agar hilang dari POS.',
                'canArchive': True,
                'menuId': menu.id,
                'usedCount': used_count
            }), 400

        name = menu.name
        db.session.delete(menu)
        db.session.commit()

        user_id = get_current_user_id()
        log_activity('DELETE_MENU', int(user_id) if user_id else None,
                     f"Deleted menu: {name}", 'Menu', id)

        return '', 204
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting menu: {e}")
        return jsonify({'error': 'Failed to delete menu', 'details': str(e)}), 500


# --- RECIPE INGREDIENTS MANAGEMENT ---

@menu_bp.route('/<int:id>/recipe', methods=['GET'])
def get_menu_recipe(id):
    try:
        menu = Menu.query.get(id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        ingredients = RecipeIngredient.query.filter_by(menuId=id).all()
        return jsonify([i.to_dict() for i in ingredients])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch menu recipe', 'details': str(e)}), 500


@menu_bp.route('/<int:id>/recipe', methods=['POST'])
def set_menu_recipe(id):
    """
    Sets the full recipe for a menu.
    Payload: { "ingredients": [ { "inventoryItemId": 1, "quantityNeeded": 18.0 }, ... ] }
    """
    try:
        menu = Menu.query.get(id)
        if not menu:
            return jsonify({'error': 'Menu not found'}), 404

        data = request.get_json() or {}
        ingredients_data = data.get('ingredients', [])

        # Remove existing recipe ingredients and replace with new ones
        RecipeIngredient.query.filter_by(menuId=id).delete()

        created_items = []
        for item in ingredients_data:
            inv_id = item.get('inventoryItemId')
            qty = float(item.get('quantityNeeded', 0))
            if inv_id and qty > 0:
                inv_item = InventoryItem.query.get(inv_id)
                if inv_item:
                    recipe_ing = RecipeIngredient(
                        menuId=id,
                        inventoryItemId=inv_id,
                        quantityNeeded=qty
                    )
                    db.session.add(recipe_ing)
                    created_items.append(recipe_ing)

        db.session.commit()
        return jsonify([i.to_dict() for i in created_items]), 200
    except Exception as e:
        db.session.rollback()
        print(f"Error setting menu recipe: {e}")
        return jsonify({'error': 'Failed to save menu recipe', 'details': str(e)}), 500


@menu_bp.route('/<int:id>/recipe/<int:recipe_id>', methods=['DELETE'])
def delete_recipe_ingredient(id, recipe_id):
    try:
        recipe_ing = RecipeIngredient.query.filter_by(id=recipe_id, menuId=id).first()
        if not recipe_ing:
            return jsonify({'error': 'Recipe ingredient not found'}), 404

        db.session.delete(recipe_ing)
        db.session.commit()
        return jsonify({'message': 'Ingredient removed from recipe'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete recipe ingredient', 'details': str(e)}), 500
