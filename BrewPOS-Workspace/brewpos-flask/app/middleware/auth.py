from functools import wraps
from flask import request, jsonify, current_app, g
import jwt

# Role hierarchy shared across the app. Anything >= HEADBAR may authorise discounts
# and void transactions.
ROLE_LEVELS = {
    'SUPERADMIN': 4,
    'ADMIN': 3,
    'OWNER': 3,
    'HEADBAR': 2,
    'CASHIER': 1
}
SUPERVISOR_LEVEL = ROLE_LEVELS['HEADBAR']


def _extract_bearer_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None
    parts = auth_header.split(' ')
    if len(parts) == 2 and parts[0].lower() == 'bearer':
        return parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def _authenticate_request():
    """
    Decode the bearer token and stash the payload on g/request.
    Returns None on success, or a (response, status) tuple to short-circuit with.
    """
    token = _extract_bearer_token()
    if not token:
        return jsonify({'error': 'Unauthorized', 'message': 'Access denied, token missing'}), 401

    try:
        secret = current_app.config['JWT_SECRET_KEY']
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        g.user = payload
        request.user = payload
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Unauthorized', 'message': 'Token has expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Unauthorized', 'message': 'Invalid token'}), 401
    except Exception as e:
        return jsonify({'error': 'Unauthorized', 'message': str(e)}), 401

    return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        failure = _authenticate_request()
        if failure:
            return failure
        return f(*args, **kwargs)
    return decorated


def setup_auth_middleware(app):
    @app.before_request
    def check_api_auth():
        # Exclude login, static web routes, and OPTIONS requests
        if request.method == 'OPTIONS':
            return
        if not request.path.startswith('/api/'):
            return
        if request.path.startswith('/api/auth/login'):
            return

        return _authenticate_request()


def get_current_user_id():
    """Helper to safely get authenticated user ID from JWT payload as int"""
    if hasattr(g, 'user') and g.user and 'id' in g.user:
        try:
            return int(g.user['id'])
        except (ValueError, TypeError):
            return None
    return None


def get_current_user():
    """Load the acting User row from the DB using the JWT id (live role, not the token snapshot)."""
    user_id = get_current_user_id()
    if not user_id:
        return None
    from app.models.user import User
    return User.query.get(user_id)


def get_current_role_level():
    """Role level of the acting user, resolved against the DB. Unknown/absent -> 0."""
    user = get_current_user()
    if not user or not user.role:
        return 0
    return ROLE_LEVELS.get(user.role.upper(), 0)


def is_supervisor():
    """True when the acting user is HEADBAR or above."""
    return get_current_role_level() >= SUPERVISOR_LEVEL


def has_role_level(minimum):
    """
    Gerbang peran untuk ambang selain supervisor -- mis. tutup buku yang hanya
    boleh diubah ADMIN ke atas. Dipakai supaya ROLE_LEVELS tidak tersalin lagi;
    sudah ada tiga salinan di repo ini (auth.py, routes/auth.py,
    routes/role_access.py) dan ketiganya harus ikut berubah setiap ada peran baru.
    """
    return get_current_role_level() >= minimum


def is_admin():
    """True when the acting user is ADMIN/OWNER or above."""
    return has_role_level(ROLE_LEVELS['ADMIN'])
