"""Reporting: completed sales and void transactions must stay in separate buckets."""
from conftest import MENU_PRICE


def _checkout(client, headers, menu, qty=1):
    res = client.post('/api/checkout', json={
        'nickname': 'Guest',
        'paymentMethod': 'CASH',
        'items': [{'menuId': menu.id, 'quantity': qty, 'price': MENU_PRICE, 'discountAmount': 0}],
    }, headers=headers)
    assert res.status_code == 201, res.get_json()
    return res.get_json()['transaction']


def test_void_is_excluded_from_sales_and_listed_separately(client, admin_headers, menu):
    kept = _checkout(client, admin_headers, menu, qty=2)
    dropped = _checkout(client, admin_headers, menu, qty=3)

    client.post(f"/api/checkout/history/{dropped['id']}/void",
                json={'voidReason': 'Salah input'}, headers=admin_headers)

    data = client.get('/api/analytics/comprehensive-reports', headers=admin_headers).get_json()

    sales_ids = [t['id'] for t in data['transactions']]
    void_ids = [t['id'] for t in data['voidTransactions']]
    assert sales_ids == [kept['id']]
    assert void_ids == [dropped['id']]

    summary = data['salesSummary']
    assert summary['totalOrders'] == 1
    assert summary['totalVoid'] == 1
    assert summary['totalVoidAmount'] == MENU_PRICE * 3
    assert summary['totalNet'] == MENU_PRICE * 2


def test_reports_empty_state(client, admin_headers):
    data = client.get('/api/analytics/comprehensive-reports', headers=admin_headers).get_json()
    assert data['transactions'] == []
    assert data['voidTransactions'] == []
    assert data['salesSummary']['totalVoidAmount'] == 0


def test_excel_export_returns_a_workbook(client, admin_headers, menu):
    """Also proves openpyxl is actually installed, which requirements.txt used to omit."""
    _checkout(client, admin_headers, menu)

    res = client.get('/api/analytics/export-excel?days=all', headers=admin_headers)
    assert res.status_code == 200, res.data[:400]
    assert res.data[:2] == b'PK'  # xlsx is a zip container


def test_excel_export_honours_a_custom_range(client, admin_headers, menu):
    _checkout(client, admin_headers, menu)

    res = client.get(
        '/api/analytics/export-excel?startDate=2000-01-01&endDate=2000-01-02',
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert res.data[:2] == b'PK'


def test_reports_need_a_token(client):
    assert client.get('/api/analytics/comprehensive-reports').status_code == 401
    assert client.get('/api/analytics/export-excel').status_code == 401
