"""Self-service profile: reading your own account and rotating your own password."""
from conftest import SEED_PASSWORD


def _login(client, username, password):
    return client.post('/api/auth/login', json={'username': username, 'password': password})


def test_me_requires_token(client):
    assert client.get('/api/auth/me').status_code == 401


def test_me_returns_the_calling_user(client, cashier_headers):
    res = client.get('/api/auth/me', headers=cashier_headers)
    assert res.status_code == 200

    me = res.get_json()
    assert me['username'] == 'kasir'
    assert me['role'] == 'CASHIER'
    assert me['landingPage'] == '/pos'


def test_me_landing_page_follows_role(client, admin_headers, headbar_headers):
    assert client.get('/api/auth/me', headers=admin_headers).get_json()['landingPage'] == '/dashboard'
    assert client.get('/api/auth/me', headers=headbar_headers).get_json()['landingPage'] == '/monitoring'


def test_cashier_can_change_own_password(client, cashier_headers):
    """PUT /users/<id> is admin-gated, so this is the only route a cashier has."""
    res = client.put('/api/auth/me/password',
                     json={'currentPassword': SEED_PASSWORD, 'newPassword': 'rahasia456'},
                     headers=cashier_headers)
    assert res.status_code == 200, res.get_json()

    assert _login(client, 'kasir', SEED_PASSWORD).status_code == 401
    assert _login(client, 'kasir', 'rahasia456').status_code == 200


def test_wrong_current_password_is_refused(client, cashier_headers):
    res = client.put('/api/auth/me/password',
                     json={'currentPassword': 'salah', 'newPassword': 'rahasia456'},
                     headers=cashier_headers)
    assert res.status_code == 401

    # The old password must still work: nothing was changed
    assert _login(client, 'kasir', SEED_PASSWORD).status_code == 200


def test_short_new_password_is_refused(client, cashier_headers):
    res = client.put('/api/auth/me/password',
                     json={'currentPassword': SEED_PASSWORD, 'newPassword': 'abc'},
                     headers=cashier_headers)
    assert res.status_code == 400
    assert _login(client, 'kasir', SEED_PASSWORD).status_code == 200


def test_reusing_the_same_password_is_refused(client, cashier_headers):
    res = client.put('/api/auth/me/password',
                     json={'currentPassword': SEED_PASSWORD, 'newPassword': SEED_PASSWORD},
                     headers=cashier_headers)
    assert res.status_code == 400


def test_password_change_needs_a_token(client):
    res = client.put('/api/auth/me/password',
                     json={'currentPassword': SEED_PASSWORD, 'newPassword': 'rahasia456'})
    assert res.status_code == 401


def test_profile_is_reachable_for_every_role(client, admin_headers, headbar_headers, cashier_headers):
    """
    initRbacNavigation() bounces the user from any path missing here, so /profile has to
    survive all three branches of get_allowed_routes().
    """
    for headers in (admin_headers, headbar_headers, cashier_headers):
        paths = client.get('/api/role-access/allowed-routes', headers=headers).get_json()['allowedPaths']
        assert '/profile' in paths


def test_profile_survives_custom_page_permissions(client, app, cashier_headers):
    """A user with a stored custom allowedPages list must not be locked out of /profile."""
    from app.extensions import db
    from app.models.user import User

    user = User.query.filter_by(username='kasir').first()
    user.allowedPages = '["/pos"]'
    db.session.commit()

    data = client.get('/api/role-access/allowed-routes', headers=cashier_headers).get_json()
    assert data['isCustom'] is True
    assert '/profile' in data['allowedPaths']


def test_profile_page_renders(client):
    assert client.get('/profile').status_code == 200
