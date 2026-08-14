import random
import math
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.customer import Customer
from app.models.transaction import Transaction, TransactionItem
from app.models.menu import Menu
from app.models.reward import Reward
from app.models.system_settings import SystemSettings
from app.models.shift import Shift
from app.services.system_logger import log_activity
from app.services.gamification_service import process_gamification_async
from app.services.inventory_service import deduct_ingredients_for_order, restore_ingredients_for_void

checkout_bp = Blueprint('checkout', __name__, url_prefix='/api/checkout')

@checkout_bp.route('/history', methods=['GET'])
def get_history():
    try:
        transactions = Transaction.query.order_by(Transaction.createdAt.desc()).limit(50).all()
        return jsonify([t.to_dict(include_items=True, include_customer=True) for t in transactions])
    except Exception as e:
        print(f"Error fetching history: {e}")
        return jsonify({'error': 'Failed to fetch history'}), 500


@checkout_bp.route('', methods=['POST'])
def checkout():
    data = request.get_json() or {}
    nickname = data.get('nickname')
    total_amount = int(data.get('totalAmount', 0))
    items = data.get('items', [])
    reward_id = data.get('rewardId')
    payment_method = data.get('paymentMethod', 'CASH')
    shift_id = data.get('shiftId')

    if not nickname:
        return jsonify({'error': 'Nickname is required'}), 400

    try:
        # Calculate points & XP: 1 pt + 1 XP per Rp 1.000
        points_earned = math.floor(total_amount / 1000)
        is_lucky_drop = False
        bonus_points = 0

        # 20% Chance for Lucky Drop
        if random.random() < 0.20 and nickname != 'Guest':
            is_lucky_drop = True
            bonus_points = 50
            points_earned += bonus_points

        if nickname == 'Guest':
            points_earned = 0
            is_lucky_drop = False
            bonus_points = 0

        # Find or create customer
        customer = Customer.query.filter_by(nickname=nickname).first()
        points_to_deduct = 0

        if reward_id:
            reward = Reward.query.get(int(reward_id))
            if not reward or not reward.active:
                return jsonify({'error': 'Reward not available or inactive'}), 400
            if not customer or customer.points < reward.pointsRequired:
                return jsonify({'error': 'Insufficient points to redeem this reward'}), 400
            points_to_deduct = reward.pointsRequired

        if not customer:
            customer = Customer(
                nickname=nickname,
                points=0,
                xp=0,
                level=1,
                streakCount=0
            )
            db.session.add(customer)
            db.session.flush()

        new_points = max(0, customer.points + points_earned - points_to_deduct)
        new_xp = customer.xp + points_earned
        new_level = math.floor(new_xp / 100) + 1

        # Point Expiration Settings
        exp_setting = SystemSettings.query.filter_by(key='POINT_EXPIRATION_DAYS').first()
        exp_days = int(exp_setting.value) if exp_setting and exp_setting.value.isdigit() else 90
        now = datetime.utcnow()
        expiry_date = now + timedelta(days=exp_days)

        # Streak calculation
        new_streak = customer.streakCount or 0
        if customer.lastVisitDate:
            last_visit = customer.lastVisitDate.date()
            today = now.date()
            diff_days = (today - last_visit).days
            if diff_days == 1:
                new_streak += 1
            elif diff_days > 1:
                new_streak = 1
        else:
            new_streak = 1

        customer.points = new_points
        customer.xp = new_xp
        customer.level = new_level
        customer.lastVisitDate = now
        customer.pointsExpiryDate = expiry_date
        customer.streakCount = new_streak

        # Employee Quota Handling
        employee_quota_used = int(data.get('employeeQuotaUsed', 0))
        if customer.customerType == 'EMPLOYEE' and employee_quota_used > 0:
            customer.check_and_reset_quota()
            customer.usedQuotaToday = min(customer.dailyQuota, (customer.usedQuotaToday or 0) + employee_quota_used)

        discount_amount = int(data.get('discountAmount', 0))

        # Tax calculation (No parking fee)
        tax_setting = SystemSettings.query.filter(SystemSettings.key.in_(['TAX_PERCENT', 'TAX_PERCENTAGE'])).first()
        tax_pct = float(tax_setting.value) if tax_setting and tax_setting.value.replace('.', '', 1).isdigit() else 11.0
        parking_fee = 0

        tax_mult = 1.0 + (tax_pct / 100.0)
        sub_total = int(round(total_amount / tax_mult)) if total_amount > 0 else 0
        tax_amount = max(0, total_amount - sub_total)

        # Menu HPP lookup
        menu_ids = [it.get('menuId') for it in items if it.get('menuId')]
        menus = Menu.query.filter(Menu.id.in_(menu_ids)).all() if menu_ids else []
        hpp_map = {m.id: m.hpp for m in menus}

        # Create Transaction
        transaction = Transaction(
            totalAmount=total_amount,
            subTotal=sub_total,
            taxAmount=tax_amount,
            parkingFee=0,
            discountAmount=discount_amount,
            pointsEarned=points_earned,
            paymentMethod=payment_method,
            customerId=customer.id,
            shiftId=int(shift_id) if shift_id else None,
            status='COMPLETED',
            createdAt=now
        )
        db.session.add(transaction)
        db.session.flush()

        # Single Unified Transaction Prefix 'TR' + yyyyMMdd + 6-digit daily sequence (Total: 16 characters, e.g. TR20260814000001)
        today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
        today_end = datetime(now.year, now.month, now.day, 23, 59, 59)
        daily_count = Transaction.query.filter(
            Transaction.createdAt >= today_start,
            Transaction.createdAt <= today_end
        ).count()

        date_str = now.strftime('%Y%m%d')
        transaction.transactionCode = f"TR{date_str}{daily_count:06d}"

        # Create Items & Deduct Ingredients
        tx_items = []
        for item in items:
            m_id = item.get('menuId')
            qty = int(item.get('quantity', 1))
            item_price = int(item.get('price', 0))
            item_disc = int(item.get('discountAmount', 0))
            item_hpp = hpp_map.get(m_id, 0)

            tx_item = TransactionItem(
                transactionId=transaction.id,
                menuId=m_id,
                quantity=qty,
                price=item_price,
                discountAmount=item_disc,
                hpp=item_hpp
            )
            db.session.add(tx_item)
            tx_items.append(tx_item)

        db.session.flush()

        # [REAL CAFE LOGIC]: Auto-deduct raw materials/inventory from stock based on recipe
        deduct_ingredients_for_order(transaction.id, tx_items)

        db.session.commit()

        # Gamification Async processing
        if nickname != 'Guest':
            process_gamification_async(customer.id, transaction.id)

        # Log Activity
        user_id_for_log = None
        if shift_id:
            shift_info = Shift.query.get(int(shift_id))
            if shift_info:
                user_id_for_log = shift_info.userId

        log_activity('TRANSACTION', user_id_for_log,
                     f"Total: Rp {total_amount:,} via {payment_method}".replace(',', '.'),
                     'Transaction', transaction.id)

        return jsonify({
            'message': 'Checkout successful',
            'customer': customer.to_dict(),
            'transaction': transaction.to_dict(include_items=True, include_customer=False),
            'luckyDrop': {'bonusPoints': bonus_points} if is_lucky_drop else None
        }), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error during checkout: {e}")
        return jsonify({'error': 'Failed to process checkout', 'details': str(e)}), 500


@checkout_bp.route('/sync', methods=['POST'])
def sync_checkout():
    data = request.get_json() or {}
    transactions_data = data.get('transactions', [])

    if not isinstance(transactions_data, list):
        return jsonify({'error': 'Invalid transactions data'}), 400

    try:
        tax_setting = SystemSettings.query.filter_by(key='TAX_PERCENTAGE').first()
        parking_setting = SystemSettings.query.filter_by(key='PARKING_FEE').first()
        exp_setting = SystemSettings.query.filter_by(key='POINT_EXPIRATION_DAYS').first()

        tax_pct = float(tax_setting.value) if tax_setting else 11.0
        cfg_parking = int(parking_setting.value) if parking_setting and parking_setting.value.isdigit() else 2000
        exp_days = int(exp_setting.value) if exp_setting and exp_setting.value.isdigit() else 90
        tax_mult = 1.0 + (tax_pct / 100.0)

        results = []
        for tx in transactions_data:
            nickname = tx.get('nickname')
            total_amount = int(tx.get('totalAmount', 0))
            items = tx.get('items', [])
            reward_id = tx.get('rewardId')
            payment_method = tx.get('paymentMethod', 'CASH')
            shift_id = tx.get('shiftId')
            created_at_str = tx.get('createdAt')

            if not nickname:
                continue

            points_earned = math.floor(total_amount / 1000)
            customer = Customer.query.filter_by(nickname=nickname).first()
            points_to_deduct = 0

            if reward_id:
                reward = Reward.query.get(int(reward_id))
                if reward and reward.active and customer and customer.points >= reward.pointsRequired:
                    points_to_deduct = reward.pointsRequired

            if not customer:
                customer = Customer(
                    nickname=nickname,
                    points=0,
                    xp=0,
                    level=1,
                    streakCount=0
                )
                db.session.add(customer)
                db.session.flush()

            new_points = max(0, customer.points + points_earned - points_to_deduct)
            new_xp = customer.xp + points_earned
            new_level = math.floor(new_xp / 100) + 1

            tx_date = datetime.fromisoformat(created_at_str.replace('Z', '+00:00')) if created_at_str else datetime.utcnow()
            expiry_date = tx_date + timedelta(days=exp_days)

            new_streak = customer.streakCount or 0
            if customer.lastVisitDate:
                last_visit = customer.lastVisitDate.date()
                curr_date = tx_date.date()
                diff = (curr_date - last_visit).days
                if diff == 1:
                    new_streak += 1
                elif diff > 1:
                    new_streak = 1
            else:
                new_streak = 1

            customer.points = new_points
            customer.xp = new_xp
            customer.level = new_level
            customer.lastVisitDate = tx_date
            customer.pointsExpiryDate = expiry_date
            customer.streakCount = new_streak

            parking_fee = cfg_parking if total_amount > cfg_parking else 0
            amount_without_parking = total_amount - parking_fee
            sub_total = int(round(amount_without_parking / tax_mult))
            tax_amount = amount_without_parking - sub_total

            menu_ids = [it.get('menuId') for it in items if it.get('menuId')]
            menus = Menu.query.filter(Menu.id.in_(menu_ids)).all() if menu_ids else []
            hpp_map = {m.id: m.hpp for m in menus}

            transaction = Transaction(
                totalAmount=total_amount,
                subTotal=sub_total,
                taxAmount=tax_amount,
                parkingFee=parking_fee,
                pointsEarned=points_earned,
                paymentMethod=payment_method,
                customerId=customer.id,
                shiftId=int(shift_id) if shift_id else None,
                createdAt=tx_date
            )
            db.session.add(transaction)
            db.session.flush()

            tx_items = []
            for it in items:
                m_id = int(it.get('menuId'))
                q = int(it.get('quantity', 1))
                p = int(it.get('price', 0))
                h = hpp_map.get(m_id, 0)
                t_item = TransactionItem(
                    transactionId=transaction.id,
                    menuId=m_id,
                    quantity=q,
                    price=p,
                    hpp=h
                )
                db.session.add(t_item)
                tx_items.append(t_item)

            db.session.flush()
            deduct_ingredients_for_order(transaction.id, tx_items)
            results.append(transaction)

        db.session.commit()

        for res_tx in results:
            process_gamification_async(res_tx.customerId, res_tx.id)

        return jsonify({'message': 'Sync successful', 'syncedCount': len(results)}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error during checkout sync: {e}")
        return jsonify({'error': 'Failed to process checkout sync'}), 500


@checkout_bp.route('/history/<int:id>/void', methods=['POST'])
def void_transaction(id):
    data = request.get_json() or {}
    void_reason = data.get('voidReason')
    voided_by = data.get('voidedBy')

    import time
    for attempt in range(3):
        try:
            transaction = Transaction.query.get(id)
            if not transaction:
                return jsonify({'error': 'Transaction not found'}), 404
            if transaction.status == 'VOID':
                return jsonify({'error': 'Transaction already voided'}), 400

            transaction.status = 'VOID'
            transaction.voidReason = void_reason
            transaction.voidedAt = datetime.utcnow()
            transaction.voidedBy = int(voided_by) if voided_by else None

            # Revert points & XP earned
            if transaction.pointsEarned > 0 and transaction.customerId:
                customer = Customer.query.get(transaction.customerId)
                if customer:
                    customer.points = max(0, customer.points - transaction.pointsEarned)
                    customer.xp = max(0, customer.xp - transaction.pointsEarned)

            # [REAL CAFE LOGIC]: Restore inventory materials
            restore_ingredients_for_void(transaction.id, transaction.items)

            db.session.commit()

            log_activity('VOID_TRANSACTION', int(voided_by) if voided_by else None,
                         void_reason, 'Transaction', transaction.id)

            return jsonify(transaction.to_dict(include_items=True, include_customer=True))
        except Exception as e:
            db.session.rollback()
            if attempt < 2 and '1205' in str(e):
                time.sleep(0.3)
                continue
            print(f"Error voiding transaction: {e}")
            return jsonify({'error': 'Failed to void transaction'}), 500
