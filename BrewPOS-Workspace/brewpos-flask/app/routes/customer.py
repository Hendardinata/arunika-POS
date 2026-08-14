from datetime import datetime
from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from app.extensions import db
from app.models.customer import Customer
from app.models.user import User
from app.services.system_logger import log_activity

customer_bp = Blueprint('customer', __name__, url_prefix='/api/customers')

def get_current_user_role():
    user_id = request.headers.get('X-User-Id')
    if user_id and user_id.isdigit():
        user = User.query.get(int(user_id))
        if user and user.role:
            return user.role.upper()
    return 'CASHIER'

@customer_bp.route('', methods=['GET'])
def get_customers():
    try:
        user_role = get_current_user_role()
        q = request.args.get('q', '').strip()
        status_filter = request.args.get('status', 'all').upper() # 'ALL', 'AKTIF', 'HILANG'
        type_filter = request.args.get('type', 'all').upper() # 'ALL', 'PELANGGAN' ('REGULAR'), 'KARYAWAN' ('EMPLOYEE')
        sort_by = request.args.get('sort', 'points') # 'points', 'latest', 'level', 'streak', 'name', 'days'

        query = Customer.query

        if q:
            query = query.filter(or_(
                Customer.nickname.ilike(f"%{q}%"),
                Customer.phone.ilike(f"%{q}%"),
                Customer.email.ilike(f"%{q}%")
            ))

        if type_filter != 'ALL':
            if type_filter in ['KARYAWAN', 'EMPLOYEE']:
                query = query.filter(Customer.customerType == 'EMPLOYEE')
            elif type_filter in ['PELANGGAN', 'REGULAR']:
                query = query.filter(Customer.customerType != 'EMPLOYEE')

        if sort_by == 'latest':
            query = query.order_by(Customer.createdAt.desc())
        elif sort_by == 'level':
            query = query.order_by(Customer.level.desc(), Customer.xp.desc())
        elif sort_by == 'streak':
            query = query.order_by(Customer.streakCount.desc())
        elif sort_by == 'name':
            query = query.order_by(Customer.nickname.asc())
        elif sort_by == 'days':
            query = query.order_by(Customer.lastVisitDate.asc())
        else: # 'points'
            query = query.order_by(Customer.points.desc())

        customers = query.all()
        result = []
        for c in customers:
            c_dict = c.to_dict(include_relations=True, user_role=user_role)
            if status_filter != 'ALL' and c_dict.get('status') != status_filter:
                continue
            result.append(c_dict)

        return jsonify(result)
    except Exception as e:
        print(f"Error fetching customers: {e}")
        return jsonify({'error': 'Failed to fetch customers', 'details': str(e)}), 500


@customer_bp.route('/autocomplete', methods=['GET'])
def autocomplete_customers():
    search_term = request.args.get('q', '').strip()
    user_role = get_current_user_role()
    try:
        query = Customer.query
        if search_term:
            query = query.filter(or_(
                Customer.nickname.ilike(f"%{search_term}%"),
                Customer.phone.ilike(f"%{search_term}%"),
                Customer.email.ilike(f"%{search_term}%")
            ))
        customers = query.order_by(Customer.points.desc()).limit(8).all()
        return jsonify([c.to_dict(include_relations=False, user_role=user_role) for c in customers])
    except Exception as e:
        return jsonify({'error': 'Autocomplete failed', 'details': str(e)}), 500


@customer_bp.route('/search', methods=['GET'])
def search_customer():
    search_term = request.args.get('nickname') or request.args.get('q') or request.args.get('id')
    if not search_term:
        return jsonify({'error': 'Search term is required'}), 400

    term = search_term.strip()
    try:
        user_role = get_current_user_role()
        customer = None
        if term.isdigit() and (request.args.get('id') or not request.args.get('nickname')):
            customer = Customer.query.get(int(term))
        if not customer:
            customer = Customer.query.filter(or_(
                Customer.nickname.ilike(term),
                Customer.phone == term,
                Customer.email.ilike(term)
            )).first()
        if not customer:
            customer = Customer.query.filter(or_(
                Customer.nickname.ilike(f"%{term}%"),
                Customer.phone.ilike(f"%{term}%"),
                Customer.email.ilike(f"%{term}%")
            )).first()

        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        customer.check_and_reset_quota()
        return jsonify(customer.to_dict(include_relations=True, user_role=user_role))
    except Exception as e:
        print(f"Error searching customer: {e}")
        return jsonify({'error': 'Failed to fetch customer'}), 500


@customer_bp.route('', methods=['POST'])
def create_customer():
    data = request.get_json() or {}
    nickname = data.get('nickname', '').strip()
    phone = data.get('phone', '').strip() if data.get('phone') else None
    email = data.get('email', '').strip() if data.get('email') else None
    customer_type = data.get('customerType', 'REGULAR')
    daily_quota = int(data.get('dailyQuota', 0))

    if not nickname:
        return jsonify({'error': 'Nama / Nickname member wajib diisi'}), 400

    # Mandatory Identity Check: Phone or Email
    if not phone and not email:
        return jsonify({'error': 'Member wajib memiliki minimal salah satu identitas kontak (Nomor Telepon atau Email)'}), 400

    try:
        user_role = get_current_user_role()
        existing = Customer.query.filter_by(nickname=nickname).first()
        if existing:
            return jsonify({'error': f'Member dengan nickname "{nickname}" sudah terdaftar'}), 400

        customer = Customer(
            nickname=nickname,
            phone=phone,
            email=email,
            customerType=customer_type,
            dailyQuota=daily_quota if customer_type == 'EMPLOYEE' else 0,
            usedQuotaToday=0,
            lastQuotaResetDate=datetime.utcnow(),
            points=0,
            xp=0,
            level=1
        )
        db.session.add(customer)
        db.session.commit()

        user_id = request.headers.get('X-User-Id')
        log_activity('CREATE_MEMBER', int(user_id) if user_id and user_id.isdigit() else None,
                     f"Created member {nickname} ({customer_type})", 'Customer', customer.id)

        return jsonify(customer.to_dict(include_relations=True, user_role=user_role)), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal menambahkan member', 'details': str(e)}), 500


@customer_bp.route('/<int:id>', methods=['PUT'])
def update_customer(id):
    data = request.get_json() or {}
    try:
        user_role = get_current_user_role()
        customer = Customer.query.get(id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        if 'nickname' in data and data['nickname'].strip():
            customer.nickname = data['nickname'].strip()

        # Phone & Email updates
        if 'phone' in data:
            customer.phone = data['phone'].strip() if data['phone'] else None
        if 'email' in data:
            customer.email = data['email'].strip() if data['email'] else None

        # Mandatory identity validation
        if not customer.phone and not customer.email:
            return jsonify({'error': 'Member wajib memiliki minimal nomor telepon atau email'}), 400

        if 'customerType' in data: customer.customerType = data['customerType']
        if 'dailyQuota' in data: customer.dailyQuota = int(data['dailyQuota'])
        if 'points' in data: customer.points = int(data['points'])

        db.session.commit()
        return jsonify(customer.to_dict(include_relations=True, user_role=user_role))
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal memperbarui member', 'details': str(e)}), 500


@customer_bp.route('/<int:id>', methods=['DELETE'])
def delete_customer(id):
    try:
        customer = Customer.query.get(id)
        if not customer:
            return jsonify({'error': 'Member tidak ditemukan'}), 404

        db.session.delete(customer)
        db.session.commit()
        return jsonify({'message': 'Member berhasil dihapus'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Gagal menghapus member', 'details': str(e)}), 500
