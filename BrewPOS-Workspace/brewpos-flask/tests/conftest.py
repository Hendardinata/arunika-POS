"""
Shared pytest fixtures. Runs against a throwaway SQLite file so the suite never touches
the MSSQL development database and can be re-run at will.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.inventory import InventoryItem  # noqa: E402
from app.models.menu import Menu, RecipeIngredient  # noqa: E402
from app.models.reward import Reward  # noqa: E402
from app.models.system_settings import SystemSettings  # noqa: E402
from app.services.db_seeder import seed_default_users  # noqa: E402

MENU_PRICE = 25000
MENU_HPP = 6000
GRAMS_PER_CUP = 18.0


@pytest.fixture
def app(tmp_path, monkeypatch):
    # A real file, not sqlite:///:memory:, so every pooled connection sees the same DB
    db_path = tmp_path / 'test.db'

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        SQLALCHEMY_ENGINE_OPTIONS = {}
        JWT_SECRET_KEY = 'test-jwt-secret'
        SECRET_KEY = 'test-secret'

    # Gamification spawns a daemon thread that would race the SQLite connection
    monkeypatch.setattr(
        'app.routes.checkout.process_gamification_async',
        lambda *args, **kwargs: None,
    )

    flask_app = create_app(TestConfig)

    with flask_app.app_context():
        # create_app runs auto_sync_schema/seed_default_users before any table exists;
        # both swallow their own errors, so build the schema and seed here instead.
        db.create_all()
        seed_default_users(flask_app)
        _seed_fixtures()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _seed_fixtures():
    bean = InventoryItem(name='Biji Kopi Arabica', unit='g', stock=1000.0, minStock=100.0, costPerUnit=200.0)
    category = Category(name='Kopi')
    db.session.add_all([bean, category])
    db.session.flush()

    menu = Menu(name='Kopi Susu Gula Aren', price=MENU_PRICE, hpp=MENU_HPP, categoryId=category.id)
    db.session.add(menu)
    db.session.flush()

    db.session.add(RecipeIngredient(menuId=menu.id, inventoryItemId=bean.id, quantityNeeded=GRAMS_PER_CUP))
    db.session.add(Reward(name='Voucher Diskon 20K', type='NORMAL', pointsRequired=100,
                          discountValue=20000, active=True))
    db.session.add(SystemSettings(key='TAX_PERCENT', value='11'))
    db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


# Seluruh akun bawaan memakai password yang sama (lihat DEFAULT_PASSWORD di db_seeder)
SEED_PASSWORD = '12qwaszx'


def _login(client, username, password):
    res = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert res.status_code == 200, res.get_json()
    return {'Authorization': f"Bearer {res.get_json()['token']}"}


@pytest.fixture
def admin_headers(client):
    """SUPERADMIN — above the HEADBAR threshold, may discount and void."""
    return _login(client, 'superadmin', SEED_PASSWORD)


@pytest.fixture
def headbar_headers(client):
    return _login(client, 'headbar', SEED_PASSWORD)


@pytest.fixture
def cashier_headers(client):
    """CASHIER — below the supervisor threshold."""
    return _login(client, 'kasir', SEED_PASSWORD)


@pytest.fixture
def menu(app):
    return Menu.query.filter_by(name='Kopi Susu Gula Aren').first()


@pytest.fixture
def bean(app):
    return InventoryItem.query.filter_by(name='Biji Kopi Arabica').first()


@pytest.fixture
def reward(app):
    return Reward.query.filter_by(name='Voucher Diskon 20K').first()


@pytest.fixture
def employee(app):
    """Employee member with a 2 cup daily quota."""
    c = Customer(nickname='Karyawan_Test', points=0, xp=0, level=1, streakCount=0,
                 customerType='EMPLOYEE', dailyQuota=2, usedQuotaToday=0)
    db.session.add(c)
    db.session.commit()
    return c
