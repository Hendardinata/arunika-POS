import bcrypt
import jwt
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, current_app
from app.extensions import db
from app.models.user import User
from app.models.expense import Expense
from app.models.shift import Shift
from app.models.transaction import Transaction
from app.services.system_logger import log_activity
from app.services import login_guard

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

ROLE_LEVELS = {
    'SUPERADMIN': 4,
    'ADMIN': 3,
    'OWNER': 3,
    'HEADBAR': 2,
    'CASHIER': 1
}

from app.middleware.auth import get_current_user_id

def get_current_actor():
    user_id = get_current_user_id()
    if user_id:
        user = User.query.get(int(user_id))
        if user:
            return user
    return None

def get_actor_role(actor):
    if not actor or not actor.role:
        return 'CASHIER'
    return actor.role.upper()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'error': 'Username dan password wajib diisi'}), 401

    # Rem dipasang sebelum query supaya percobaan yang tertahan tidak menyentuh
    # DB sama sekali.
    locked_for = login_guard.seconds_until_unlocked(username)
    if locked_for:
        return jsonify({
            'error': f'Terlalu banyak percobaan login. Coba lagi dalam {locked_for // 60 + 1} menit.'
        }), 429

    try:
        u_clean = username.strip()
        user = User.query.filter(db.func.lower(User.username) == u_clean.lower()).first()
        if not user:
            login_guard.record_failure(username)
            return jsonify({'error': 'Username atau password salah'}), 401

        # Check password with bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            login_guard.record_failure(username)
            return jsonify({'error': 'Username atau password salah'}), 401

        login_guard.clear(username)
        secret = current_app.config['JWT_SECRET_KEY']
        token_payload = {
            'id': user.id,
            'username': user.username,
            'role': user.role,
            'assignedShift': user.assignedShift,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        token = jwt.encode(token_payload, secret, algorithm='HS256')

        # Default landing page based on role
        landing_page = '/dashboard'
        if user.role == 'CASHIER':
            landing_page = '/pos'
        elif user.role == 'HEADBAR':
            landing_page = '/monitoring'

        return jsonify({
            'message': 'Login berhasil',
            'token': token,
            'landingPage': landing_page,
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
                'assignedShift': user.assignedShift
            }
        })
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Terjadi kesalahan sistem saat login'}), 500


@auth_bp.route('/me', methods=['GET'])
def get_my_profile():
    """Own account. Anyone with a valid token may read this, regardless of role."""
    actor = get_current_actor()
    if not actor:
        return jsonify({'error': 'Sesi tidak valid'}), 401

    role = get_actor_role(actor)
    landing = '/pos'
    if role in ('SUPERADMIN', 'ADMIN', 'OWNER'):
        landing = '/dashboard'
    elif role == 'HEADBAR':
        landing = '/monitoring'

    data = actor.to_dict()
    data['landingPage'] = landing
    return jsonify(data)


@auth_bp.route('/me/password', methods=['PUT'])
def change_my_password():
    """
    Self-service password change. PUT /users/<id> is gated to admin roles, so without
    this a cashier has no way to rotate their own password.
    """
    actor = get_current_actor()
    if not actor:
        return jsonify({'error': 'Sesi tidak valid'}), 401

    data = request.get_json() or {}
    current_password = str(data.get('currentPassword') or '')
    new_password = str(data.get('newPassword') or '').strip()

    if not current_password or not new_password:
        return jsonify({'error': 'Password lama dan password baru wajib diisi'}), 400

    if len(new_password) < 6:
        return jsonify({'error': 'Password baru minimal 6 karakter'}), 400

    if not bcrypt.checkpw(current_password.encode('utf-8'), actor.password.encode('utf-8')):
        return jsonify({'error': 'Password lama tidak cocok'}), 401

    if bcrypt.checkpw(new_password.encode('utf-8'), actor.password.encode('utf-8')):
        return jsonify({'error': 'Password baru harus berbeda dari password lama'}), 400

    try:
        actor.password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        db.session.commit()
        log_activity('CHANGE_PASSWORD', actor.id, f"User {actor.username} mengganti password sendiri", 'User', actor.id)
        return jsonify({'message': 'Password berhasil diperbarui'})
    except Exception as e:
        db.session.rollback()
        print(f"Change password error: {e}")
        return jsonify({'error': 'Gagal memperbarui password'}), 500


@auth_bp.route('/users', methods=['GET'])
def get_users():
    try:
        users = User.query.all()
        return jsonify([u.to_dict() for u in users])
    except Exception as e:
        return jsonify({'error': 'Gagal mengambil data user'}), 500


@auth_bp.route('/users', methods=['POST'])
def create_user():
    actor = get_current_actor()
    actor_role = get_actor_role(actor)
    actor_lvl = ROLE_LEVELS.get(actor_role, 1)

    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'CASHIER').upper()
    assigned_shift = data.get('assignedShift')

    if not username or not password:
        return jsonify({'error': 'Username dan password wajib diisi'}), 400

    target_lvl = ROLE_LEVELS.get(role, 1)

    # Hierarchy Check: Cannot create user with higher or equal role unless superadmin
    if actor_role != 'SUPERADMIN':
        if target_lvl >= 4 or role == 'SUPERADMIN':
            return jsonify({'error': 'Hanya Superadmin yang dapat membuat user dengan hak akses Superadmin!'}), 403
        if actor_lvl < target_lvl:
            return jsonify({'error': f'Role {actor_role} tidak diizinkan membuat user dengan hak akses {role}!'}), 403

    try:
        existing = User.query.filter_by(username=username).first()
        if existing:
            return jsonify({'error': f'Username "{username}" sudah digunakan'}), 400

        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user = User(
            username=username,
            password=hashed,
            role=role,
            assignedShift=assigned_shift
        )
        db.session.add(user)
        db.session.commit()

        log_activity('CREATE_USER', actor.id if actor else None,
                     f"Created user: {username} (Role: {role})", 'User', user.id)

        return jsonify(user.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal membuat user baru', 'details': str(e)}), 500


@auth_bp.route('/users/<int:id>', methods=['PUT'])
def update_user(id):
    actor = get_current_actor()
    actor_role = get_actor_role(actor)
    actor_lvl = ROLE_LEVELS.get(actor_role, 1)

    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')
    if role: role = role.upper()
    assigned_shift = data.get('assignedShift')

    try:
        target_user = User.query.get(id)
        if not target_user:
            return jsonify({'error': 'User tidak ditemukan'}), 404

        target_current_lvl = ROLE_LEVELS.get(target_user.role, 1)

        # Hierarchy Validation:
        if actor_role != 'SUPERADMIN':
            # Cannot edit a superadmin unless you are superadmin
            if target_user.role == 'SUPERADMIN' or target_current_lvl >= 4:
                return jsonify({'error': 'Hanya Superadmin yang dapat mengedit akun Superadmin!'}), 403
            
            # Cannot promote someone to SUPERADMIN
            if role == 'SUPERADMIN':
                return jsonify({'error': 'Hanya Superadmin yang dapat memberikan hak akses Superadmin!'}), 403
            
            # Cannot edit a user with higher rank
            if actor_lvl < target_current_lvl and (not actor or actor.id != target_user.id):
                return jsonify({'error': f'Anda tidak memiliki hak akses untuk mengedit user {target_user.username}'}), 403

        if role:
            target_user.role = role
        if assigned_shift is not None:
            target_user.assignedShift = assigned_shift

        if username and username.strip() != '' and username.strip() != target_user.username:
            exists = User.query.filter_by(username=username.strip()).first()
            if exists:
                return jsonify({'error': f'Username "{username}" sudah digunakan'}), 400
            target_user.username = username.strip()

        if password and str(password).strip() != '':
            target_user.password = bcrypt.hashpw(str(password).strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        db.session.commit()

        log_activity('UPDATE_USER', actor.id if actor else None,
                     f"Updated user: {target_user.username} (Role: {target_user.role})", 'User', target_user.id)

        return jsonify(target_user.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal memperbarui user', 'details': str(e)}), 500


@auth_bp.route('/users/<int:id>', methods=['DELETE'])
def delete_user(id):
    actor = get_current_actor()
    actor_role = get_actor_role(actor)

    try:
        user = User.query.get(id)
        if not user:
            return jsonify({'error': 'User tidak ditemukan'}), 404

        # Hierarchy Validation for Deletion
        if actor_role != 'SUPERADMIN':
            if user.role == 'SUPERADMIN':
                return jsonify({'error': 'Hanya Superadmin yang dapat menghapus akun Superadmin!'}), 403
            if user.role in ['ADMIN', 'OWNER'] and actor_role not in ['ADMIN', 'OWNER']:
                return jsonify({'error': 'Anda tidak berhak menghapus akun Admin/Owner!'}), 403

        # Protect last superadmin / owner
        if user.role == 'SUPERADMIN':
            sa_count = User.query.filter_by(role='SUPERADMIN').count()
            if sa_count <= 1:
                return jsonify({'error': 'Tidak dapat menghapus satu-satunya akun Superadmin sistem!'}), 400

        if user.role in ['OWNER', 'ADMIN']:
            admin_count = User.query.filter(User.role.in_(['OWNER', 'ADMIN', 'SUPERADMIN'])).count()
            if admin_count <= 1:
                return jsonify({'error': 'Tidak dapat menghapus akun administrator terakhir'}), 400

        fallback_user = User.query.filter(User.role.in_(['SUPERADMIN', 'OWNER', 'ADMIN']), User.id != id).first()
        if fallback_user:
            Expense.query.filter_by(userId=id).update({'userId': fallback_user.id})
            Shift.query.filter_by(userId=id).update({'userId': fallback_user.id})
        else:
            Expense.query.filter_by(userId=id).delete()
            shifts = Shift.query.filter_by(userId=id).all()
            for s in shifts:
                Transaction.query.filter_by(shiftId=s.id).update({'shiftId': None})
            Shift.query.filter_by(userId=id).delete()

        db.session.delete(user)
        db.session.commit()

        log_activity('DELETE_USER', actor.id if actor else None,
                     f"Deleted user ID: {id} ({user.username})", 'User', id)

        return jsonify({'message': f'User {user.username} berhasil dihapus'})
    except Exception as e:
        db.session.rollback()
        print(f"Delete user error: {e}")
        return jsonify({'error': 'Gagal menghapus user', 'details': str(e)}), 500
