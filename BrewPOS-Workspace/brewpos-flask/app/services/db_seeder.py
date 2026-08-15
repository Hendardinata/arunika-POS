import bcrypt
from datetime import datetime
from app.extensions import db
from app.models.user import User
from app.models.app_menu import AppMenu, RoleAccess

# Satu akun per hak akses. assignedShift sudah tidak dipakai (tidak ada shift
# tetap; kasir mana pun ikut sesi kas toko yang sedang terbuka).
DEFAULT_PASSWORD = '12qwaszx'

DEFAULT_USERS = [
    {
        'username': 'superadmin',
        'password': DEFAULT_PASSWORD,
        'role': 'SUPERADMIN',
        'assignedShift': None
    },
    {
        'username': 'owner',
        'password': DEFAULT_PASSWORD,
        'role': 'ADMIN',
        'assignedShift': None
    },
    {
        'username': 'headbar',
        'password': DEFAULT_PASSWORD,
        'role': 'HEADBAR',
        'assignedShift': None
    },
    {
        'username': 'kasir',
        'password': DEFAULT_PASSWORD,
        'role': 'CASHIER',
        'assignedShift': None
    }
]

APP_PAGES = [
    {'name': 'Dashboard Analitik', 'path': '/dashboard', 'icon': 'chart-pie'},
    {'name': 'POS Kasir', 'path': '/pos', 'icon': 'cash-register'},
    {'name': 'Live Monitoring / KDS', 'path': '/monitoring', 'icon': 'tv'},
    {'name': 'Menu & Resep Bahan', 'path': '/menus', 'icon': 'mug-hot'},
    {'name': 'Inventori & Opname', 'path': '/inventory', 'icon': 'boxes-stacked'},
    {'name': 'Member & Loyalty CRM', 'path': '/customers', 'icon': 'users'},
    {'name': 'Pengeluaran Toko', 'path': '/expenses', 'icon': 'receipt'},
    {'name': 'Pusat Laporan Lengkap', 'path': '/reports', 'icon': 'file-invoice-dollar'},
    {'name': 'Pengaturan Sistem & Hak Akses', 'path': '/settings', 'icon': 'gear'}
]

DEFAULT_ROLE_PERMISSIONS = {
    'SUPERADMIN': ['/dashboard', '/pos', '/monitoring', '/menus', '/inventory', '/customers', '/expenses', '/reports', '/settings'],
    'ADMIN': ['/dashboard', '/pos', '/monitoring', '/menus', '/inventory', '/customers', '/expenses', '/reports', '/settings'],
    'OWNER': ['/dashboard', '/pos', '/monitoring', '/menus', '/inventory', '/customers', '/expenses', '/reports', '/settings'],
    'HEADBAR': ['/pos', '/monitoring', '/menus', '/inventory', '/expenses'],
    'CASHIER': ['/pos', '/monitoring', '/customers']
}

def seed_default_users(app):
    """
    Seeds default system accounts and page permissions for all 4 RBAC user roles.
    """
    with app.app_context():
        try:
            # 1. Sync & Seed Users
            # Only create missing accounts. Never overwrite an existing password, or a
            # password changed through the UI would silently revert on the next restart.
            for item in DEFAULT_USERS:
                existing = User.query.filter_by(username=item['username']).first()
                if not existing:
                    hashed = bcrypt.hashpw(item['password'].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    user = User(
                        username=item['username'],
                        password=hashed,
                        role=item['role'],
                        assignedShift=item['assignedShift']
                    )
                    db.session.add(user)
                    print(f"[Seed] Created user: {item['username']} ({item['role']})")
                elif existing.role != item['role']:
                    existing.role = item['role']

            # 2. Sync App Menus
            menu_map = {}
            for p in APP_PAGES:
                menu = AppMenu.query.filter_by(path=p['path']).first()
                if not menu:
                    menu = AppMenu(name=p['name'], path=p['path'], icon=p['icon'])
                    db.session.add(menu)
                    db.session.flush()
                else:
                    menu.name = p['name']
                    menu.icon = p['icon']
                menu_map[p['path']] = menu

            db.session.flush()

            # 3. Sync Default RoleAccess
            for role_name, allowed_paths in DEFAULT_ROLE_PERMISSIONS.items():
                for path, menu in menu_map.items():
                    can_view = (path in allowed_paths)
                    existing_ra = RoleAccess.query.filter_by(role=role_name, appMenuId=menu.id).first()
                    if not existing_ra:
                        ra = RoleAccess(
                            role=role_name,
                            appMenuId=menu.id,
                            canView=can_view,
                            canEdit=can_view
                        )
                        db.session.add(ra)
                    else:
                        existing_ra.canView = can_view
                        existing_ra.canEdit = can_view

            db.session.commit()
            print("[Seed] Seed users and page permissions verified successfully.")
        except Exception as e:
            db.session.rollback()
            print(f"[Seed] User and permission seed warning: {e}")
