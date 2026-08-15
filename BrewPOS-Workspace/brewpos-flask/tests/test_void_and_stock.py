"""Ingredient deduction, void restoration, and void authorisation."""
from app.extensions import db
from app.models.transaction import Transaction

from conftest import GRAMS_PER_CUP, MENU_PRICE


def _checkout(client, headers, menu, qty=2, nickname='Guest'):
    res = client.post('/api/checkout', json={
        'nickname': nickname,
        'paymentMethod': 'CASH',
        'items': [{'menuId': menu.id, 'quantity': qty, 'price': MENU_PRICE, 'discountAmount': 0}],
    }, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()['transaction']


def test_checkout_deducts_recipe_ingredients(client, cashier_headers, menu, bean):
    before = bean.stock
    _checkout(client, cashier_headers, menu, qty=2)

    db.session.refresh(bean)
    assert bean.stock == before - (GRAMS_PER_CUP * 2)


def test_void_restores_ingredients(client, admin_headers, menu, bean):
    before = bean.stock
    tx = _checkout(client, admin_headers, menu, qty=3)

    res = client.post(f"/api/checkout/history/{tx['id']}/void",
                      json={'voidReason': 'Salah pesan'}, headers=admin_headers)
    assert res.status_code == 200, res.get_json()

    db.session.refresh(bean)
    assert bean.stock == before


def test_void_attribution_comes_from_the_token(client, admin_headers, menu):
    """A forged voidedBy in the body must be ignored."""
    tx = _checkout(client, admin_headers, menu)

    res = client.post(f"/api/checkout/history/{tx['id']}/void",
                      json={'voidReason': 'Test', 'voidedBy': 999999},
                      headers=admin_headers)
    assert res.status_code == 200

    voided = Transaction.query.get(tx['id'])
    assert voided.voidedBy != 999999
    assert voided.status == 'VOID'
    assert voided.voidedAt is not None


def test_cashier_cannot_void(client, cashier_headers, menu, bean):
    tx = _checkout(client, cashier_headers, menu)
    before = bean.stock

    res = client.post(f"/api/checkout/history/{tx['id']}/void",
                      json={'voidReason': 'Diam-diam'}, headers=cashier_headers)
    assert res.status_code == 403

    db.session.refresh(bean)
    assert bean.stock == before  # nothing restored, nothing changed
    assert Transaction.query.get(tx['id']).status == 'COMPLETED'


def test_double_void_rejected(client, admin_headers, menu):
    tx = _checkout(client, admin_headers, menu)
    first = client.post(f"/api/checkout/history/{tx['id']}/void",
                        json={'voidReason': 'Sekali'}, headers=admin_headers)
    assert first.status_code == 200

    second = client.post(f"/api/checkout/history/{tx['id']}/void",
                         json={'voidReason': 'Dua kali'}, headers=admin_headers)
    assert second.status_code == 400


def test_void_unknown_transaction(client, admin_headers):
    res = client.post('/api/checkout/history/999999/void',
                      json={'voidReason': 'x'}, headers=admin_headers)
    assert res.status_code == 404


def test_void_reverts_loyalty_points(client, admin_headers, menu):
    # Member harus didaftarkan lebih dulu (wajib punya HP atau email); checkout
    # tidak lagi membuat member otomatis dari nickname yang belum dikenal.
    reg = client.post('/api/customers',
                      json={'nickname': 'Poin_Test', 'phone': '081200000001'},
                      headers=admin_headers)
    assert reg.status_code == 201, reg.get_json()

    tx = _checkout(client, admin_headers, menu, qty=4, nickname='Poin_Test')
    assert tx['pointsEarned'] > 0

    client.post(f"/api/checkout/history/{tx['id']}/void",
                json={'voidReason': 'Batal'}, headers=admin_headers)

    from app.models.customer import Customer
    customer = Customer.query.filter_by(nickname='Poin_Test').first()
    assert customer.points == 0
