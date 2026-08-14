import bcrypt
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.system_settings import SystemSettings
from app.models.category import Category
from app.models.menu import Menu, RecipeIngredient
from app.models.inventory import InventoryItem, InventoryLog
from app.models.expense import ExpenseCategory
from app.models.quest import Quest
from app.models.badge import Badge
from app.models.reward import Reward
from app.models.app_menu import AppMenu, RoleAccess

def seed_database():
    app = create_app()
    with app.app_context():
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        print(f"Creating all tables in MSSQL database ({db_uri.split('/')[-1].split('?')[0]})...")
        db.create_all()
        print("Tables created successfully!")

        # 1. Default System Users (All 4 RBAC Roles)
        users_to_seed = [
            {'username': 'superadmin', 'password': 'superadmin123', 'role': 'SUPERADMIN', 'shift': None},
            {'username': 'owner', 'password': 'owner123', 'role': 'ADMIN', 'shift': None},
            {'username': 'admin', 'password': 'owner123', 'role': 'ADMIN', 'shift': None},
            {'username': 'headbar', 'password': 'headbar123', 'role': 'HEADBAR', 'shift': 'MORNING'},
            {'username': 'kasir', 'password': 'kasir123', 'role': 'CASHIER', 'shift': 'MORNING'},
        ]
        for u_data in users_to_seed:
            hashed_pw = bcrypt.hashpw(u_data['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            existing_user = User.query.filter_by(username=u_data['username']).first()
            if not existing_user:
                new_u = User(
                    username=u_data['username'],
                    password=hashed_pw,
                    role=u_data['role'],
                    assignedShift=u_data['shift']
                )
                db.session.add(new_u)
                print(f"[Seed] Created user: {u_data['username']} ({u_data['role']})")
            else:
                existing_user.password = hashed_pw
                existing_user.role = u_data['role']
                print(f"[Seed] Updated user password & role: {u_data['username']} ({u_data['role']})")

        # 2. System Settings
        settings_data = [
            ('POINT_EXPIRATION_DAYS', '90', 'Masa kedaluwarsa loyalty poin dalam satuan hari'),
            ('TAX_PERCENTAGE', '11', 'Persentase Pajak PB1/PPN yang termasuk dalam harga'),
            ('PARKING_FEE', '2000', 'Nominal biaya parkir/layanan')
        ]
        for key, val, desc in settings_data:
            st = SystemSettings.query.filter_by(key=key).first()
            if not st:
                db.session.add(SystemSettings(key=key, value=val, description=desc))
                print(f"[Seed] Created setting: {key} = {val}")

        # 3. Expense Categories
        expense_cats = ['Bahan Baku', 'Operasional', 'Gaji', 'Sewa', 'Lain-lain']
        for cat_name in expense_cats:
            if not ExpenseCategory.query.filter_by(name=cat_name).first():
                db.session.add(ExpenseCategory(name=cat_name))
                print(f"[Seed] Created expense category: {cat_name}")

        # 4. App Menus & Role Access
        app_menus_data = [
            ("Dashboard Analitik", "/dashboard", "chart-bar"),
            ("POS Kasir", "/pos", "shopping-cart"),
            ("Kelola Menu", "/menus", "coffee"),
            ("Inventori & Resep", "/inventory", "box"),
            ("Pelanggan & CRM", "/customers", "users"),
            ("Pengeluaran", "/expenses", "receipt"),
            ("Laporan", "/reports", "file-text"),
            ("Pengaturan", "/settings", "settings")
        ]
        for name, path, icon in app_menus_data:
            am = AppMenu.query.filter_by(path=path).first()
            if not am:
                am = AppMenu(name=name, path=path, icon=icon)
                db.session.add(am)
                db.session.flush()
                # Create default access
                for r in ['OWNER', 'ADMIN', 'HEADBAR', 'CASHIER']:
                    can_edit = True if r in ['OWNER', 'ADMIN'] else False
                    db.session.add(RoleAccess(role=r, appMenuId=am.id, canView=True, canEdit=can_edit))
                print(f"[Seed] Created AppMenu: {name}")

        # 5. Product Categories
        categories = ['Coffee', 'Non-Coffee', 'Pastry & Food', 'Signature']
        cat_map = {}
        for cat_name in categories:
            cat = Category.query.filter_by(name=cat_name).first()
            if not cat:
                cat = Category(name=cat_name)
                db.session.add(cat)
                db.session.flush()
                print(f"[Seed] Created Category: {cat_name}")
            cat_map[cat_name] = cat

        # 6. Inventory Items (Raw Materials)
        inventory_items_data = [
            ("Biji Kopi Arabica", 5000.0, "gram"),      # 5 kg
            ("Susu Fresh Milk", 10000.0, "ml"),         # 10 L
            ("Sirup Gula Aren", 3000.0, "ml"),          # 3 L
            ("Sirup Karamel", 1500.0, "ml"),            # 1.5 L
            ("Bubuk Matcha Premium", 1000.0, "gram"),   # 1 kg
            ("Cup Dingin 16oz", 250.0, "pcs"),          # 250 pcs
            ("Cup Panas 8oz", 200.0, "pcs"),            # 200 pcs
            ("Sedotan Ramah Lingkungan", 300.0, "pcs"), # 300 pcs
            ("Dough Croissant", 50.0, "pcs")            # 50 pcs
        ]
        inv_map = {}
        for name, stock, unit in inventory_items_data:
            inv = InventoryItem.query.filter_by(name=name).first()
            if not inv:
                inv = InventoryItem(name=name, stock=stock, unit=unit)
                db.session.add(inv)
                db.session.flush()
                db.session.add(InventoryLog(itemId=inv.id, quantity=stock, type='IN', notes='Initial seed stock'))
                print(f"[Seed] Created Inventory Item: {name} ({stock} {unit})")
            inv_map[name] = inv

        # 7. Menus + Recipe Ingredients
        menus_data = [
            {
                "name": "Espresso Single",
                "category": "Coffee",
                "price": 18000,
                "hpp": 5000,
                "description": "Ekstrak kopi murni 30ml dengan crema tebal dan aroma khas Nusantara.",
                "recipe": [
                    ("Biji Kopi Arabica", 18.0),
                    ("Cup Panas 8oz", 1.0)
                ]
            },
            {
                "name": "Kopi Susu Gula Aren",
                "category": "Signature",
                "price": 25000,
                "hpp": 8500,
                "description": "Espresso blend spesial dipadukan susu creamy dan manis legit gula aren asli.",
                "recipe": [
                    ("Biji Kopi Arabica", 18.0),
                    ("Susu Fresh Milk", 120.0),
                    ("Sirup Gula Aren", 25.0),
                    ("Cup Dingin 16oz", 1.0),
                    ("Sedotan Ramah Lingkungan", 1.0)
                ]
            },
            {
                "name": "Caramel Macchiato",
                "category": "Coffee",
                "price": 32000,
                "hpp": 11000,
                "description": "Espresso berlapis susu lembut dengan drizzle saus karamel premium.",
                "recipe": [
                    ("Biji Kopi Arabica", 18.0),
                    ("Susu Fresh Milk", 150.0),
                    ("Sirup Karamel", 20.0),
                    ("Cup Dingin 16oz", 1.0),
                    ("Sedotan Ramah Lingkungan", 1.0)
                ]
            },
            {
                "name": "Matcha Latte",
                "category": "Non-Coffee",
                "price": 28000,
                "hpp": 9500,
                "description": "Teh hijau Uji Kyoto dipadukan susu segar nan lembut.",
                "recipe": [
                    ("Bubuk Matcha Premium", 15.0),
                    ("Susu Fresh Milk", 150.0),
                    ("Cup Dingin 16oz", 1.0),
                    ("Sedotan Ramah Lingkungan", 1.0)
                ]
            },
            {
                "name": "Butter Croissant",
                "category": "Pastry & Food",
                "price": 22000,
                "hpp": 10000,
                "description": "Pastry renyah berlapis dengan aroma butter Prancis yang harum.",
                "recipe": [
                    ("Dough Croissant", 1.0)
                ]
            }
        ]

        for m_data in menus_data:
            m = Menu.query.filter_by(name=m_data['name']).first()
            if not m:
                cat_obj = cat_map.get(m_data['category'])
                m = Menu(
                    name=m_data['name'],
                    categoryId=cat_obj.id if cat_obj else 1,
                    price=m_data['price'],
                    hpp=m_data['hpp'],
                    description=m_data['description']
                )
                db.session.add(m)
                db.session.flush()

                # Add recipe ingredients
                for ing_name, qty in m_data.get('recipe', []):
                    inv_obj = inv_map.get(ing_name)
                    if inv_obj:
                        db.session.add(RecipeIngredient(
                            menuId=m.id,
                            inventoryItemId=inv_obj.id,
                            quantityNeeded=qty
                        ))
                print(f"[Seed] Created Menu with Recipe: {m.name}")

        # 8. Gamification Quests, Badges, Rewards
        quests_data = [
            ("Pecinta Kopi Harian", "Beli 1 minuman apapun hari ini", "TOTAL_TRANSACTIONS", 1, 50, 100, True),
            ("Sultan Kafe", "Total transaksi akumulasi mencapai Rp 100.000", "TOTAL_SPEND", 100000, 150, 300, False),
            ("Jelajah Rasa: Aren", "Coba menu Kopi Susu Gula Aren sebanyak 3 kali", "BUY_ITEM", 3, 100, 200, False)
        ]
        for q_name, q_desc, q_type, q_target, q_pts, q_xp, q_daily in quests_data:
            if not Quest.query.filter_by(name=q_name).first():
                db.session.add(Quest(
                    name=q_name, description=q_desc, type=q_type,
                    targetValue=q_target, rewardPoints=q_pts, rewardXp=q_xp,
                    isDaily=q_daily, active=True
                ))
                print(f"[Seed] Created Quest: {q_name}")

        badges_data = [
            ("First Sip", "Transaksi pertama Anda di Arunika", None, 1),
            ("Coffee Regular", "Telah bertransaksi sebanyak 5 kali", None, 5),
            ("Master Brewer", "Telah bertransaksi sebanyak 20 kali", None, 20)
        ]
        for b_name, b_desc, b_icon, b_req in badges_data:
            if not Badge.query.filter_by(name=b_name).first():
                db.session.add(Badge(name=b_name, description=b_desc, iconUrl=b_icon, requiredTransactions=b_req))
                print(f"[Seed] Created Badge: {b_name}")

        rewards_data = [
            ("Diskon Rp 10.000", "Potongan langsung Rp 10.000 untuk transaksi berikutnya", 100, "NORMAL"),
            ("Free Pastry", "Gratis 1 Croissant pilihan", 250, "NORMAL"),
            ("Mystery Coffee Gift", "Hadiah merchandise atau kopi spesial kejutan", 500, "MYSTERY_BOX")
        ]
        for r_name, r_desc, r_pts, r_type in rewards_data:
            if not Reward.query.filter_by(name=r_name).first():
                db.session.add(Reward(name=r_name, description=r_desc, pointsRequired=r_pts, type=r_type, active=True))
                print(f"[Seed] Created Reward: {r_name}")

        db.session.commit()
        print("\n[SUCCESS] Seeding completed successfully! Database is ready to use.")

if __name__ == '__main__':
    seed_database()
