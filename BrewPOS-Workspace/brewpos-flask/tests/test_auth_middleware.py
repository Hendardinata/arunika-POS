"""Global /api/* auth gate (app/middleware/auth.py)."""
from datetime import datetime, timedelta

import jwt


def test_api_requires_token(client):
    res = client.get('/api/settings')
    assert res.status_code == 401
    assert res.get_json()['message'] == 'Access denied, token missing'


def test_api_accepts_valid_token(client, admin_headers):
    res = client.get('/api/settings', headers=admin_headers)
    assert res.status_code == 200


def test_login_stays_public(client):
    res = client.post('/api/auth/login', json={'username': 'kasir', 'password': 'kasir123'})
    assert res.status_code == 200
    assert res.get_json()['token']


def test_login_rejects_bad_password(client):
    res = client.post('/api/auth/login', json={'username': 'kasir', 'password': 'salah'})
    assert res.status_code == 401


def test_garbage_token_rejected(client):
    res = client.get('/api/settings', headers={'Authorization': 'Bearer not-a-jwt'})
    assert res.status_code == 401
    assert res.get_json()['message'] == 'Invalid token'


def test_expired_token_rejected(client, app):
    stale = jwt.encode(
        {'id': 1, 'role': 'SUPERADMIN', 'exp': datetime.utcnow() - timedelta(hours=1)},
        app.config['JWT_SECRET_KEY'],
        algorithm='HS256',
    )
    res = client.get('/api/settings', headers={'Authorization': f'Bearer {stale}'})
    assert res.status_code == 401
    assert res.get_json()['message'] == 'Token has expired'


def test_token_signed_with_wrong_secret_rejected(client):
    forged = jwt.encode(
        {'id': 1, 'role': 'SUPERADMIN', 'exp': datetime.utcnow() + timedelta(hours=1)},
        'attacker-secret',
        algorithm='HS256',
    )
    res = client.get('/api/settings', headers={'Authorization': f'Bearer {forged}'})
    assert res.status_code == 401


def test_web_pages_are_not_gated(client):
    """Only /api/* is behind the token; the login page must still render."""
    assert client.get('/login').status_code == 200
