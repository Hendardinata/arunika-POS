from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.menu import Menu, RecipeIngredient
from app.models.inventory import InventoryItem

recipe_bp = Blueprint('recipe', __name__, url_prefix='/api/recipes')

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
