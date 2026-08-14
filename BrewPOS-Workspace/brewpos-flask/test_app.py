import json
from app import create_app
from app.extensions import db
from app.models import (
    User, Menu, InventoryItem, Category, Customer,
    Transaction, SystemSettings, RecipeIngredient
)

def test_everything():
    app = create_app()
    with app.app_context():
        print("=== 1. VERIFYING MODELS & DATA ===")
        users = User.query.all()
        print(f"Users found ({len(users)}): {[u.username for u in users]}")

        menus = Menu.query.all()
        print(f"Menus found ({len(menus)}): {[m.name for m in menus]}")

        inv_items = InventoryItem.query.all()
        print(f"Inventory items found ({len(inv_items)}): {[f'{i.name} ({i.stock} {i.unit})' for i in inv_items]}")

        kopi_aren = Menu.query.filter_by(name='Kopi Susu Gula Aren').first()
        print(f"Recipe ingredients for '{kopi_aren.name}':")
        for r in kopi_aren.recipeIngredients:
            print(f"  - {r.inventoryItem.name}: {r.quantityNeeded} {r.inventoryItem.unit}")

        print("\n=== 2. TESTING CHECKOUT & AUTO-DEDUCT INGREDIENTS ===")
        # Get stock of Arabica, Fresh Milk, Gula Aren, Cup, Straw
        biji_kopi = InventoryItem.query.filter_by(name='Biji Kopi Arabica').first()
        fresh_milk = InventoryItem.query.filter_by(name='Susu Fresh Milk').first()
        initial_kopi_stock = biji_kopi.stock
        initial_milk_stock = fresh_milk.stock

        print(f"Initial Biji Kopi Stock: {initial_kopi_stock} g")
        print(f"Initial Fresh Milk Stock: {initial_milk_stock} ml")

        # Simulate checkout of 2x Kopi Susu Gula Aren
        client = app.test_client()
        checkout_payload = {
            "nickname": "Budi_Tester",
            "totalAmount": 50000,
            "paymentMethod": "CASH",
            "items": [
                {
                    "menuId": kopi_aren.id,
                    "quantity": 2,
                    "price": kopi_aren.price
                }
            ]
        }
        res = client.post('/api/checkout', json=checkout_payload)
        print(f"Checkout Response Status: {res.status_code}")
        res_data = res.get_json()
        print("Checkout Result:", json.dumps(res_data, indent=2))

        # Check stock deduction
        db.session.expire_all()
        biji_kopi_after = InventoryItem.query.filter_by(name='Biji Kopi Arabica').first()
        fresh_milk_after = InventoryItem.query.filter_by(name='Susu Fresh Milk').first()

        print(f"After Checkout Biji Kopi: {biji_kopi_after.stock} g (Expected: {initial_kopi_stock - 36.0} g)")
        print(f"After Checkout Fresh Milk: {fresh_milk_after.stock} ml (Expected: {initial_milk_stock - 240.0} ml)")

        assert biji_kopi_after.stock == initial_kopi_stock - 36.0, "Kopi stock did not deduct properly!"
        assert fresh_milk_after.stock == initial_milk_stock - 240.0, "Milk stock did not deduct properly!"
        print("[PASSED] Real cafe recipe ingredient auto-deduction works perfectly!")

        print("\n=== 3. TESTING VOID TRANSACTION & RESTORATION ===")
        tx_id = res_data['transaction']['id']
        void_res = client.post(f'/api/checkout/history/{tx_id}/void', json={
            'voidReason': 'Customer salah pesan',
            'voidedBy': 1
        })
        print(f"Void Response Status: {void_res.status_code}")
        db.session.expire_all()
        biji_kopi_restored = InventoryItem.query.filter_by(name='Biji Kopi Arabica').first()
        fresh_milk_restored = InventoryItem.query.filter_by(name='Susu Fresh Milk').first()

        print(f"After Void Biji Kopi: {biji_kopi_restored.stock} g (Expected: {initial_kopi_stock} g)")
        print(f"After Void Fresh Milk: {fresh_milk_restored.stock} ml (Expected: {initial_milk_stock} ml)")

        assert biji_kopi_restored.stock == initial_kopi_stock, "Kopi stock not restored!"
        assert fresh_milk_restored.stock == initial_milk_stock, "Milk stock not restored!"
        print("[PASSED] Void stock restoration works perfectly!")

        print("\n=== 4. TESTING AUTH LOGIN API ===")
        login_res = client.post('/api/auth/login', json={'username': 'admin', 'password': '123'})
        print("Login status:", login_res.status_code)
        token = login_res.get_json().get('token')
        print("Received JWT token length:", len(token) if token else 0)
        assert token is not None, "Login did not return token!"

        print("\n=== 5. TESTING ANALYTICS API ===")
        analytics_res = client.get('/api/analytics?days=7')
        print("Analytics status:", analytics_res.status_code)
        print("Analytics summary:", analytics_res.get_json())

        print("\n[ALL TESTS PASSED SUCCESSFULLY!]")

if __name__ == '__main__':
    test_everything()
