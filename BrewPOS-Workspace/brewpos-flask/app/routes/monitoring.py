from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from sqlalchemy import func
from app.extensions import db
from app.models.transaction import Transaction, TransactionItem
from app.models.inventory import InventoryItem
from app.models.shift import Shift
from app.models.system_log import SystemLog
from app.services.system_logger import log_activity
from app.middleware.auth import get_current_user_id

monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/api/monitoring')

@monitoring_bp.route('/kds', methods=['GET'])
def get_kds_orders():
    """
    Returns active orders for the Barista / Kitchen Display System.
    """
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get active orders from today (exclude VOID and already SERVED unless requested)
        show_all = request.args.get('all') == 'true'
        tx_query = Transaction.query.filter(
            Transaction.createdAt >= today_start,
            Transaction.status != 'VOID'
        ).order_by(Transaction.createdAt.desc())

        transactions = tx_query.all()
        kds_orders = []

        for tx in transactions:
            prep_status = getattr(tx, 'prepStatus', None) or 'QUEUED'
            # If voidReason starts with PREP:, treat as prepStatus
            if tx.voidReason and tx.voidReason.startswith('PREP:'):
                prep_status = tx.voidReason.replace('PREP:', '')

            if not show_all and prep_status == 'SERVED':
                continue

            elapsed_minutes = int((now - tx.createdAt).total_seconds() / 60) if tx.createdAt else 0

            items_list = []
            for it in tx.items:
                recipe_notes = it.menu.recipeNotes if it.menu else ''
                items_list.append({
                    'id': it.id,
                    'menuId': it.menuId,
                    'name': it.menu.name if it.menu else f"Menu #{it.menuId}",
                    'quantity': it.quantity,
                    'category': it.menu.category.name if it.menu and it.menu.category else 'Minuman',
                    'recipeNotes': recipe_notes
                })

            kds_orders.append({
                'id': tx.id,
                'customerName': tx.customer.nickname if tx.customer else 'Guest',
                'createdAt': tx.createdAt.isoformat() if tx.createdAt else None,
                'elapsedMinutes': elapsed_minutes,
                'prepStatus': prep_status,
                'paymentMethod': tx.paymentMethod,
                'totalAmount': tx.totalAmount,
                'items': items_list
            })

        return jsonify(kds_orders)
    except Exception as e:
        print(f"Error fetching KDS: {e}")
        return jsonify({'error': 'Failed to fetch KDS orders', 'details': str(e)}), 500


@monitoring_bp.route('/kds/<int:id>/status', methods=['PUT'])
def update_kds_status(id):
    data = request.get_json() or {}
    new_status = data.get('status', 'PREPARING') # QUEUED, PREPARING, READY, SERVED

    try:
        tx = Transaction.query.get(id)
        if not tx:
            return jsonify({'error': 'Order not found'}), 404

        tx.voidReason = f"PREP:{new_status}"
        db.session.commit()

        user_id = get_current_user_id()
        user_id_int = int(user_id) if user_id else None
        log_activity('KDS_STATUS_CHANGE', user_id_int,
                     f"Order #{id} status changed to {new_status}", 'Transaction', id)

        return jsonify({'message': f'Order #{id} status updated to {new_status}', 'status': new_status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update order status', 'details': str(e)}), 500


@monitoring_bp.route('/low-stock', methods=['GET'])
def get_low_stock_alerts():
    """
    Returns items where stock <= minStock
    """
    try:
        items = InventoryItem.query.all()
        alerts = []
        for it in items:
            min_stk = getattr(it, 'minStock', 10.0) or 10.0
            cur_stk = it.stock or 0.0
            if cur_stk <= min_stk:
                alerts.append({
                    'id': it.id,
                    'name': it.name,
                    'stock': cur_stk,
                    'unit': it.unit,
                    'minStock': min_stk,
                    'deficit': round(min_stk - cur_stk, 1)
                })
        return jsonify(alerts)
    except Exception as e:
        return jsonify({'error': 'Failed to fetch low stock alerts', 'details': str(e)}), 500


@monitoring_bp.route('/live-telemetry', methods=['GET'])
def get_live_telemetry():
    """
    Returns live shift & cash telemetry
    """
    try:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Active shift
        active_shift = Shift.query.filter_by(status='OPEN').order_by(Shift.startTime.desc()).first()
        shift_data = None
        current_cash_in_drawer = 0

        if active_shift:
            # Calculate cash transactions in this shift
            cash_sales = db.session.query(func.sum(Transaction.totalAmount)).filter(
                Transaction.shiftId == active_shift.id,
                Transaction.status == 'COMPLETED',
                Transaction.paymentMethod == 'CASH'
            ).scalar() or 0

            current_cash_in_drawer = active_shift.startingCash + cash_sales
            shift_data = {
                'id': active_shift.id,
                'type': active_shift.type,
                'cashier': active_shift.user.username if active_shift.user else 'Kasir',
                'startTime': active_shift.startTime.isoformat(),
                'startingCash': active_shift.startingCash,
                'cashSales': cash_sales,
                'currentCashInDrawer': current_cash_in_drawer
            }

        # Today's aggregated stats
        today_tx = Transaction.query.filter(
            Transaction.createdAt >= today_start,
            Transaction.status == 'COMPLETED'
        ).all()

        total_orders_today = len(today_tx)
        total_revenue_today = sum(t.totalAmount for t in today_tx)
        total_cups_today = sum(sum(it.quantity for it in t.items) for t in today_tx)

        # Pending KDS count
        pending_count = sum(1 for t in today_tx if not t.voidReason or not t.voidReason.startswith('PREP:SERVED'))

        return jsonify({
            'activeShift': shift_data,
            'currentCashInDrawer': current_cash_in_drawer,
            'totalOrdersToday': total_orders_today,
            'totalRevenueToday': total_revenue_today,
            'totalCupsToday': total_cups_today,
            'pendingOrdersCount': pending_count,
            'serverTime': now.isoformat()
        })
    except Exception as e:
        print(f"Error fetching live telemetry: {e}")
        return jsonify({'error': 'Failed to fetch live telemetry', 'details': str(e)}), 500


@monitoring_bp.route('/recent-activities', methods=['GET'])
def get_recent_activities():
    try:
        logs = SystemLog.query.order_by(SystemLog.createdAt.desc()).limit(25).all()
        return jsonify([l.to_dict() for l in logs])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch recent activities', 'details': str(e)}), 500
