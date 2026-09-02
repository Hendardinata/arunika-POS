from app.routes.auth import auth_bp
from app.routes.category import category_bp
from app.routes.menu import menu_bp
from app.routes.checkout import checkout_bp
from app.routes.customer import customer_bp
from app.routes.analytics import analytics_bp
from app.routes.gamification import gamification_bp
from app.routes.inventory import inventory_bp
from app.routes.expenses import expenses_bp
from app.routes.settings import settings_bp
from app.routes.shift import shift_bp
from app.routes.attendance import attendance_bp
from app.routes.role_access import role_access_bp
from app.routes.recipe import recipe_bp
from app.routes.logs import logs_bp
from app.routes.historical_sales import historical_bp
from app.routes.notifications import notifications_bp
from app.routes.bootstrap import bootstrap_bp
from app.routes.monitoring import monitoring_bp
from app.routes.database import database_bp, unduh_bp
from app.routes.web import web_bp

__all__ = [
    'auth_bp',
    'category_bp',
    'menu_bp',
    'checkout_bp',
    'customer_bp',
    'analytics_bp',
    'gamification_bp',
    'inventory_bp',
    'expenses_bp',
    'settings_bp',
    'shift_bp',
    'attendance_bp',
    'role_access_bp',
    'recipe_bp',
    'logs_bp',
    'historical_bp',
    'notifications_bp',
    'bootstrap_bp',
    'monitoring_bp',
    'database_bp',
    'unduh_bp',
    'web_bp'
]
