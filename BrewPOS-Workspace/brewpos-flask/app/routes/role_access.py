import json
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.app_menu import AppMenu, RoleAccess
from app.models.user import User
from app.services.system_logger import log_activity

role_access_bp = Blueprint('role_access', __name__, url_prefix='/api/role-access')

ROLE_LEVELS = {
    'SUPERADMIN': 4,
    'ADMIN': 3,
    'OWNER': 3,
    'HEADBAR': 2,
    'CASHIER': 1
}

def get_current_actor():
    user_id = request.headers.get('X-User-Id')
    if user_id and user_id.isdigit():
        user = User.query.get(int(user_id))
        if user:
            return user
    return None

def get_current_user_role():
    actor = get_current_actor()
    return actor.role.upper() if actor and actor.role else 'CASHIER'


@role_access_bp.route('/menus', methods=['GET'])
def get_app_menus():
    try:
        menus = AppMenu.query.order_by(AppMenu.id.asc()).all()
        return jsonify([m.to_dict() for m in menus])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch app menus'}), 500


@role_access_bp.route('/allowed-routes', methods=['GET'])
def get_allowed_routes():
    """
    Returns the list of allowed paths and default landing page for the current logged-in user.
    Supports user-level custom page permissions override.
    """
    try:
        actor = get_current_actor()
        role = actor.role.upper() if actor and actor.role else 'CASHIER'
        
        # 1. Superadmin has unrestricted access to all pages
        if role == 'SUPERADMIN':
            menus = AppMenu.query.all()
            return jsonify({
                'role': role,
                'isCustom': False,
                'landingPage': '/dashboard',
                'allowedPaths': [m.path for m in menus]
            })

        # 2. Check if user has explicit custom allowedPages configured
        if actor:
            custom_pages = actor.get_custom_allowed_pages()
            if custom_pages is not None:
                landing = '/pos'
                if '/dashboard' in custom_pages: landing = '/dashboard'
                elif '/monitoring' in custom_pages: landing = '/monitoring'
                elif custom_pages: landing = custom_pages[0]

                return jsonify({
                    'role': role,
                    'isCustom': True,
                    'landingPage': landing,
                    'allowedPaths': custom_pages
                })

        # 3. Fallback to RoleAccess configured for role
        accesses = RoleAccess.query.filter_by(role=role, canView=True).all()
        allowed_paths = [a.appMenu.path for a in accesses if a.appMenu]

        landing_page = '/pos'
        if role in ['ADMIN', 'OWNER']:
            landing_page = '/dashboard'
        elif role == 'HEADBAR':
            landing_page = '/monitoring'

        return jsonify({
            'role': role,
            'isCustom': False,
            'landingPage': landing_page,
            'allowedPaths': allowed_paths
        })
    except Exception as e:
        return jsonify({'error': 'Failed to fetch allowed routes', 'details': str(e)}), 500


@role_access_bp.route('/user/<int:user_id>', methods=['GET'])
def get_user_page_access(user_id):
    """
    Get custom page access details for a specific user.
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        menus = AppMenu.query.order_by(AppMenu.id.asc()).all()
        custom_pages = user.get_custom_allowed_pages()
        
        # Default role pages
        role_accesses = RoleAccess.query.filter_by(role=user.role, canView=True).all()
        role_default_paths = [ra.appMenu.path for ra in role_accesses if ra.appMenu]

        return jsonify({
            'user': user.to_dict(),
            'hasCustomAccess': custom_pages is not None,
            'allowedPages': custom_pages if custom_pages is not None else role_default_paths,
            'roleDefaultPages': role_default_paths,
            'allMenus': [m.to_dict() for m in menus]
        })
    except Exception as e:
        return jsonify({'error': 'Failed to fetch user access', 'details': str(e)}), 500


@role_access_bp.route('/user/<int:user_id>', methods=['PUT'])
def update_user_page_access(user_id):
    """
    Configure specific user page permissions (User-Level Access).
    """
    actor = get_current_actor()
    actor_role = get_actor_role(actor)
    actor_lvl = ROLE_LEVELS.get(actor_role, 1)

    if actor_role not in ['SUPERADMIN', 'ADMIN', 'OWNER']:
        return jsonify({'error': 'Hanya Superadmin dan Admin yang dapat mengatur hak akses user!'}), 403

    try:
        target_user = User.query.get(user_id)
        if not target_user:
            return jsonify({'error': 'User tidak ditemukan'}), 404

        target_lvl = ROLE_LEVELS.get(target_user.role, 1)

        # Hierarchy protection: Admin cannot edit Superadmin's access
        if actor_role != 'SUPERADMIN' and (target_user.role == 'SUPERADMIN' or target_lvl >= 4):
            return jsonify({'error': 'Hanya Superadmin yang dapat mengatur hak akses akun Superadmin!'}), 403

        data = request.get_json() or {}
        use_custom = bool(data.get('useCustom', False))
        allowed_pages = data.get('allowedPages', [])

        if use_custom:
            if not isinstance(allowed_pages, list):
                return jsonify({'error': 'Daftar halaman tidak valid'}), 400
            target_user.allowedPages = json.dumps(allowed_pages)
        else:
            # Revert to role default
            target_user.allowedPages = None

        db.session.commit()

        log_activity('UPDATE_USER_PERMISSIONS', actor.id if actor else None,
                     f"Updated page permissions for user: {target_user.username} (Custom: {use_custom})",
                     'User', target_user.id)

        return jsonify({
            'message': f'Hak akses halaman untuk {target_user.username} berhasil disimpan!',
            'user': target_user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal menyimpan hak akses user', 'details': str(e)}), 500


def get_actor_role(actor):
    if not actor or not actor.role:
        return 'CASHIER'
    return actor.role.upper()


@role_access_bp.route('/matrix', methods=['GET'])
def get_permission_matrix():
    try:
        menus = AppMenu.query.order_by(AppMenu.id.asc()).all()
        roles = ['SUPERADMIN', 'ADMIN', 'HEADBAR', 'CASHIER']
        accesses = RoleAccess.query.all()

        access_map = {}
        for a in accesses:
            access_map[(a.role, a.appMenuId)] = {
                'canView': a.canView,
                'canEdit': a.canEdit
            }

        matrix = []
        for m in menus:
            row = {
                'id': m.id,
                'name': m.name,
                'path': m.path,
                'icon': m.icon,
                'permissions': {}
            }
            for r in roles:
                if r == 'SUPERADMIN':
                    row['permissions'][r] = {'canView': True, 'canEdit': True, 'locked': True}
                else:
                    perm = access_map.get((r, m.id), {'canView': False, 'canEdit': False})
                    row['permissions'][r] = {
                        'canView': perm['canView'],
                        'canEdit': perm['canEdit'],
                        'locked': False
                    }
            matrix.append(row)

        return jsonify({'menus': matrix, 'roles': roles})
    except Exception as e:
        return jsonify({'error': 'Failed to fetch matrix', 'details': str(e)}), 500


@role_access_bp.route('/matrix', methods=['PUT'])
def update_permission_matrix():
    actor_role = get_current_user_role()
    if actor_role not in ['SUPERADMIN', 'ADMIN', 'OWNER']:
        return jsonify({'error': 'Hanya Superadmin dan Admin yang dapat mengatur hak akses halaman!'}), 403

    data = request.get_json() or {}
    updates = data.get('matrix', [])
    user_id = request.headers.get('X-User-Id')

    try:
        for item in updates:
            menu_id = item.get('menuId')
            role = item.get('role', '').upper()
            can_view = bool(item.get('canView', True))
            can_edit = bool(item.get('canEdit', False))

            if role == 'SUPERADMIN' and actor_role != 'SUPERADMIN':
                continue

            existing = RoleAccess.query.filter_by(role=role, appMenuId=menu_id).first()
            if existing:
                existing.canView = can_view
                existing.canEdit = can_edit
            else:
                ra = RoleAccess(
                    role=role,
                    appMenuId=menu_id,
                    canView=can_view,
                    canEdit=can_edit
                )
                db.session.add(ra)

        db.session.commit()
        log_activity('UPDATE_PERMISSION_MATRIX', int(user_id) if user_id and user_id.isdigit() else None,
                     "Updated Application Page Permissions Matrix")

        return jsonify({'message': 'Matriks hak akses halaman berhasil disimpan'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal menyimpan matriks hak akses', 'details': str(e)}), 500
