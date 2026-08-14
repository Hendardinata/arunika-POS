from app.extensions import db
from app.models.menu import Menu, RecipeIngredient
from app.models.inventory import InventoryItem, InventoryLog

def deduct_ingredients_for_order(transaction_id, items):
    """
    Deduct inventory stock automatically based on recipe ingredients of each ordered menu.
    """
    try:
        for item in items:
            menu_id = item.menuId if hasattr(item, 'menuId') else item.get('menuId')
            quantity = item.quantity if hasattr(item, 'quantity') else item.get('quantity', 1)
            menu = Menu.query.get(menu_id)
            menu_name = menu.name if menu else f"Menu #{menu_id}"

            recipes = RecipeIngredient.query.filter_by(menuId=menu_id).all()
            for recipe in recipes:
                deduct_qty = float(recipe.quantityNeeded) * float(quantity)
                inv_item = InventoryItem.query.get(recipe.inventoryItemId)
                if inv_item:
                    inv_item.stock = (inv_item.stock or 0.0) - deduct_qty
                    log = InventoryLog(
                        itemId=inv_item.id,
                        quantity=deduct_qty,
                        type='OUT',
                        notes=f"Auto Deduct: Order #{transaction_id} ({quantity}x {menu_name})"
                    )
                    db.session.add(log)
        db.session.flush()
    except Exception as e:
        print(f"[InventoryService] Error deducting ingredients: {e}")
        raise e


def restore_ingredients_for_void(transaction_id, items):
    """
    Restore inventory stock when a transaction is voided.
    """
    try:
        for item in items:
            menu_id = item.menuId if hasattr(item, 'menuId') else item.get('menuId')
            quantity = item.quantity if hasattr(item, 'quantity') else item.get('quantity', 1)
            menu = Menu.query.get(menu_id)
            menu_name = menu.name if menu else f"Menu #{menu_id}"

            recipes = RecipeIngredient.query.filter_by(menuId=menu_id).all()
            for recipe in recipes:
                restore_qty = float(recipe.quantityNeeded) * float(quantity)
                inv_item = InventoryItem.query.get(recipe.inventoryItemId)
                if inv_item:
                    inv_item.stock = (inv_item.stock or 0.0) + restore_qty
                    log = InventoryLog(
                        itemId=inv_item.id,
                        quantity=restore_qty,
                        type='IN',
                        notes=f"Void Reversal: Order #{transaction_id} ({quantity}x {menu_name})"
                    )
                    db.session.add(log)
        db.session.flush()
    except Exception as e:
        print(f"[InventoryService] Error restoring ingredients: {e}")
        raise e
