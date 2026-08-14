import threading
from flask import current_app
from app.extensions import db
from app.models.customer import Customer, CustomerQuest, CustomerBadge
from app.models.quest import Quest
from app.models.badge import Badge
from app.models.transaction import Transaction

def _process_gamification(app, customer_id, transaction_id):
    with app.app_context():
        try:
            transaction = Transaction.query.get(transaction_id)
            customer = Customer.query.get(customer_id)
            if not transaction or not customer:
                return

            # --- 1. EVALUATE QUESTS ---
            active_quests = Quest.query.filter_by(active=True).all()
            for quest in active_quests:
                cq = CustomerQuest.query.filter_by(customerId=customer_id, questId=quest.id).first()
                if not cq:
                    cq = CustomerQuest(customerId=customer_id, questId=quest.id, progress=0, isCompleted=False)
                    db.session.add(cq)
                    db.session.flush()

                if not cq.isCompleted:
                    added_progress = 0

                    if quest.type == 'TOTAL_TRANSACTIONS':
                        added_progress = 1
                    elif quest.type == 'TOTAL_SPEND':
                        added_progress = transaction.totalAmount
                    elif quest.type == 'BUY_ITEM' and quest.targetEntityId:
                        matching_items = [it for it in transaction.items if it.menuId == quest.targetEntityId]
                        added_progress = sum(it.quantity for it in matching_items)

                    if added_progress > 0:
                        cq.progress += added_progress
                        if cq.progress >= quest.targetValue:
                            cq.isCompleted = True
                            customer.points += quest.rewardPoints
                            customer.xp += quest.rewardXp
                            print(f"[Gamification] Customer {customer.nickname} completed quest '{quest.name}'")

            # --- 2. EVALUATE BADGES ---
            badges = Badge.query.all()
            total_tx_count = Transaction.query.filter_by(customerId=customer_id, status='COMPLETED').count()

            for badge in badges:
                has_badge = CustomerBadge.query.filter_by(customerId=customer_id, badgeId=badge.id).first()
                if not has_badge:
                    if badge.requiredTransactions > 0 and total_tx_count >= badge.requiredTransactions:
                        cb = CustomerBadge(customerId=customer_id, badgeId=badge.id)
                        db.session.add(cb)
                        print(f"[Gamification] Customer {customer.nickname} unlocked badge '{badge.name}'")

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"[Gamification] Error processing gamification: {e}")

def process_gamification_async(customer_id, transaction_id):
    """
    Spawns a background thread to process quests & badges non-blockingly.
    """
    app = current_app._get_current_object()
    thread = threading.Thread(target=_process_gamification, args=(app, customer_id, transaction_id))
    thread.daemon = True
    thread.start()
