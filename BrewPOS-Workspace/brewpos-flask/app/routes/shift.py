from datetime import datetime
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.shift import Shift
from app.models.user import User
from app.models.transaction import Transaction
from app.middleware.auth import token_required

shift_bp = Blueprint('shift', __name__, url_prefix='/api/shift')

@shift_bp.route('/open', methods=['POST'])
@token_required
def open_shift():
    data = request.get_json() or {}
    starting_cash = int(data.get('startingCash', 0))
    user_id = g.user.get('id')

    try:
        existing = Shift.query.filter_by(userId=user_id, status='OPEN').first()
        if existing:
            return jsonify({'error': 'You already have an open shift', 'shift': existing.to_dict()}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        shift_type = user.assignedShift or 'MORNING'

        shift = Shift(
            userId=user_id,
            type=shift_type,
            status='OPEN',
            startingCash=starting_cash,
            startTime=datetime.utcnow()
        )
        db.session.add(shift)
        db.session.commit()

        return jsonify(shift.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error opening shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/current', methods=['GET'])
@token_required
def get_current_shift():
    user_id = g.user.get('id')
    try:
        shift = Shift.query.filter_by(userId=user_id, status='OPEN').first()
        return jsonify({'currentShift': shift.to_dict() if shift else None})
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/close', methods=['POST'])
@token_required
def close_shift():
    data = request.get_json() or {}
    ending_cash = int(data.get('endingCash', 0))
    user_id = g.user.get('id')

    try:
        shift = Shift.query.filter_by(userId=user_id, status='OPEN').first()
        if not shift:
            return jsonify({'error': 'No open shift found'}), 404

        # Calculate expected cash from CASH transactions
        cash_income = 0
        transactions = Transaction.query.filter_by(shiftId=shift.id, status='COMPLETED').all()
        for t in transactions:
            if t.paymentMethod == 'CASH':
                cash_income += t.totalAmount

        expected_ending_cash = shift.startingCash + cash_income

        shift.status = 'CLOSED'
        shift.endTime = datetime.utcnow()
        shift.endingCash = ending_cash
        shift.expectedEndingCash = expected_ending_cash

        db.session.commit()
        return jsonify(shift.to_dict())
    except Exception as e:
        db.session.rollback()
        print(f"Error closing shift: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@shift_bp.route('/reports', methods=['GET'])
def get_shift_reports():
    try:
        shifts = Shift.query.order_by(Shift.createdAt.desc()).limit(50).all()
        return jsonify([s.to_dict(include_transactions=True) for s in shifts])
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
