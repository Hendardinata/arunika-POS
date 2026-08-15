"""
Server-side pricing rules in app/routes/checkout.py.

The client may not decide what anything costs: line prices come from the Menu table,
reward discounts come from Reward.discountValue, employee freebies come from the
customer's remaining quota, and any other discount needs HEADBAR+ authorisation.
"""
from app.extensions import db
from app.models.customer import Customer
from app.models.transaction import Transaction

from conftest import MENU_PRICE


def _order(menu, qty=1, item_discount=0, **extra):
    payload = {
        'nickname': 'Guest',
        'paymentMethod': 'CASH',
        'items': [{
            'menuId': menu.id,
            'quantity': qty,
            'price': MENU_PRICE,
            'discountAmount': item_discount,
        }],
    }
    payload.update(extra)
    return payload


def test_client_price_is_ignored(client, cashier_headers, menu):
    """A tampered unit price must not reach the database."""
    payload = _order(menu)
    payload['items'][0]['price'] = 1
    payload['totalAmount'] = 1

    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 201, res.get_json()

    tx = res.get_json()['transaction']
    assert tx['totalAmount'] == MENU_PRICE
    assert tx['items'][0]['price'] == MENU_PRICE


def test_cashier_manual_discount_is_refused(client, cashier_headers, menu):
    res = client.post('/api/checkout',
                      json=_order(menu, discountAmount=999999),
                      headers=cashier_headers)
    assert res.status_code == 403
    assert 'Head Barista' in res.get_json()['error']
    assert Transaction.query.count() == 0


def test_supervisor_manual_discount_is_clamped_to_gross(client, headbar_headers, menu):
    res = client.post('/api/checkout',
                      json=_order(menu, discountAmount=999999),
                      headers=headbar_headers)
    assert res.status_code == 201, res.get_json()

    tx = res.get_json()['transaction']
    assert tx['discountAmount'] == MENU_PRICE  # clamped, never more than the order
    assert tx['totalAmount'] == 0


def test_cashier_item_discount_without_quota_is_dropped(client, cashier_headers, menu):
    """Waiving each line's full price is exactly how a tampered cart zeroes an order."""
    res = client.post('/api/checkout',
                      json=_order(menu, qty=2, item_discount=MENU_PRICE),
                      headers=cashier_headers)
    assert res.status_code == 201, res.get_json()

    tx = res.get_json()['transaction']
    assert tx['items'][0]['discountAmount'] == 0
    assert tx['totalAmount'] == MENU_PRICE * 2


def test_reward_discount_comes_from_the_database(client, cashier_headers, menu, reward):
    """The client sends 999999; only reward.discountValue counts."""
    customer = Customer(nickname='Member_Test', points=500, xp=0, level=1, streakCount=0)
    db.session.add(customer)
    db.session.commit()

    payload = _order(menu, qty=3, nickname='Member_Test',
                     rewardId=reward.id, discountAmount=999999)
    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 201, res.get_json()

    tx = res.get_json()['transaction']
    assert tx['discountAmount'] == reward.discountValue
    assert tx['totalAmount'] == MENU_PRICE * 3 - reward.discountValue


def test_reward_requires_enough_points(client, cashier_headers, menu, reward):
    customer = Customer(nickname='Miskin_Test', points=1, xp=0, level=1, streakCount=0)
    db.session.add(customer)
    db.session.commit()

    payload = _order(menu, nickname='Miskin_Test', rewardId=reward.id)
    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 400
    assert Transaction.query.count() == 0


def test_employee_quota_caps_free_cups(client, cashier_headers, menu, employee):
    """dailyQuota is 2; asking for 5 free cups must not be granted."""
    payload = _order(menu, qty=5, item_discount=MENU_PRICE,
                     nickname=employee.nickname, employeeQuotaUsed=5)
    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 201, res.get_json()

    tx = res.get_json()['transaction']
    assert tx['items'][0]['discountAmount'] == 0  # 5 > 2 remaining, so nothing is waived
    assert tx['totalAmount'] == MENU_PRICE * 5

    db.session.refresh(employee)
    assert employee.usedQuotaToday == 0


def test_employee_quota_is_honoured_within_limit(client, cashier_headers, menu, employee):
    payload = _order(menu, qty=2, item_discount=MENU_PRICE, nickname=employee.nickname)
    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 201, res.get_json()

    assert res.get_json()['transaction']['totalAmount'] == 0
    db.session.refresh(employee)
    assert employee.usedQuotaToday == 2


def test_employee_quota_does_not_stack_across_orders(client, cashier_headers, menu, employee):
    first = _order(menu, qty=2, item_discount=MENU_PRICE, nickname=employee.nickname)
    assert client.post('/api/checkout', json=first, headers=cashier_headers).status_code == 201

    second = _order(menu, qty=1, item_discount=MENU_PRICE, nickname=employee.nickname)
    res = client.post('/api/checkout', json=second, headers=cashier_headers)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()['transaction']['totalAmount'] == MENU_PRICE  # quota spent


def test_empty_items_rejected(client, cashier_headers):
    res = client.post('/api/checkout',
                      json={'nickname': 'Guest', 'items': []},
                      headers=cashier_headers)
    assert res.status_code == 400


def test_zero_quantity_rejected(client, cashier_headers, menu):
    res = client.post('/api/checkout', json=_order(menu, qty=0), headers=cashier_headers)
    assert res.status_code == 400
    assert Transaction.query.count() == 0


def test_negative_quantity_rejected(client, cashier_headers, menu):
    res = client.post('/api/checkout', json=_order(menu, qty=-3), headers=cashier_headers)
    assert res.status_code == 400


def test_unknown_menu_rejected(client, cashier_headers, menu):
    payload = _order(menu)
    payload['items'][0]['menuId'] = 999999
    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 404
    assert Transaction.query.count() == 0


def test_string_menu_id_is_coerced(client, cashier_headers, menu):
    """Offline clients serialise ids as strings; that must not silently drop the order."""
    payload = _order(menu)
    payload['items'][0]['menuId'] = str(menu.id)
    res = client.post('/api/checkout', json=payload, headers=cashier_headers)
    assert res.status_code == 201, res.get_json()


def test_tax_split_is_consistent(client, cashier_headers, menu):
    res = client.post('/api/checkout', json=_order(menu, qty=4), headers=cashier_headers)
    tx = res.get_json()['transaction']
    assert tx['subTotal'] + tx['taxAmount'] == tx['totalAmount']


def test_zero_tax_handling(client, cashier_headers, menu):
    from app.models.system_settings import SystemSettings
    # Set tax to 0%
    st = SystemSettings.query.filter_by(key='TAX_PERCENT').first()
    if not st:
        st = SystemSettings(key='TAX_PERCENT', value='0')
        db.session.add(st)
    else:
        st.value = '0'
    db.session.commit()

    res = client.post('/api/checkout', json=_order(menu, qty=2), headers=cashier_headers)
    assert res.status_code == 201
    tx = res.get_json()['transaction']
    assert tx['taxAmount'] == 0
    assert tx['subTotal'] == tx['totalAmount']


def test_checkout_needs_a_token(client, menu):
    assert client.post('/api/checkout', json=_order(menu)).status_code == 401

