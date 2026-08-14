import random
from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.quest import Quest
from app.models.badge import Badge
from app.models.reward import Reward
from app.models.customer import Customer, CustomerBadge

gamification_bp = Blueprint('gamification', __name__, url_prefix='/api/gamification')

# --- QUESTS ---

@gamification_bp.route('/quests', methods=['GET'])
def get_quests():
    try:
        quests = Quest.query.filter_by(active=True).all()
        return jsonify([q.to_dict() for q in quests])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch quests'}), 500

@gamification_bp.route('/quests', methods=['POST'])
def create_quest():
    data = request.get_json() or {}
    try:
        quest = Quest(
            name=data.get('name'),
            description=data.get('description'),
            targetValue=int(data.get('targetValue', 1)),
            rewardPoints=int(data.get('rewardPoints', 0)),
            rewardXp=int(data.get('rewardXp', 0)),
            type=data.get('type', 'TOTAL_TRANSACTIONS'),
            targetEntityId=int(data.get('targetEntityId')) if data.get('targetEntityId') else None,
            isDaily=bool(data.get('isDaily', False))
        )
        db.session.add(quest)
        db.session.commit()
        return jsonify(quest.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create quest', 'details': str(e)}), 500

@gamification_bp.route('/quests/<int:id>', methods=['PUT'])
def update_quest(id):
    data = request.get_json() or {}
    try:
        quest = Quest.query.get(id)
        if not quest:
            return jsonify({'error': 'Quest not found'}), 404

        if 'name' in data: quest.name = data['name']
        if 'description' in data: quest.description = data['description']
        if 'targetValue' in data: quest.targetValue = int(data['targetValue'])
        if 'rewardPoints' in data: quest.rewardPoints = int(data['rewardPoints'])
        if 'rewardXp' in data: quest.rewardXp = int(data['rewardXp'])
        if 'type' in data: quest.type = data['type']
        if 'targetEntityId' in data: quest.targetEntityId = int(data['targetEntityId']) if data['targetEntityId'] else None
        if 'isDaily' in data: quest.isDaily = bool(data['isDaily'])

        db.session.commit()
        return jsonify(quest.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update quest'}), 500

@gamification_bp.route('/quests/<int:id>', methods=['DELETE'])
def delete_quest(id):
    try:
        quest = Quest.query.get(id)
        if not quest:
            return jsonify({'error': 'Quest not found'}), 404

        quest.active = False
        db.session.commit()
        return jsonify({'message': 'Quest deleted (soft)', 'quest': quest.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete quest'}), 500


# --- BADGES ---

@gamification_bp.route('/badges', methods=['GET'])
def get_badges():
    try:
        badges = Badge.query.all()
        return jsonify([b.to_dict() for b in badges])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch badges'}), 500

@gamification_bp.route('/badges', methods=['POST'])
def create_badge():
    data = request.get_json() or {}
    try:
        badge = Badge(
            name=data.get('name'),
            description=data.get('description'),
            iconUrl=data.get('iconUrl'),
            requiredTransactions=int(data.get('requiredTransactions', 0))
        )
        db.session.add(badge)
        db.session.commit()
        return jsonify(badge.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create badge'}), 500

@gamification_bp.route('/badges/<int:id>', methods=['PUT'])
def update_badge(id):
    data = request.get_json() or {}
    try:
        badge = Badge.query.get(id)
        if not badge:
            return jsonify({'error': 'Badge not found'}), 404

        if 'name' in data: badge.name = data['name']
        if 'description' in data: badge.description = data['description']
        if 'iconUrl' in data: badge.iconUrl = data['iconUrl']
        if 'requiredTransactions' in data: badge.requiredTransactions = int(data['requiredTransactions'])

        db.session.commit()
        return jsonify(badge.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update badge'}), 500

@gamification_bp.route('/badges/<int:id>', methods=['DELETE'])
def delete_badge(id):
    try:
        badge = Badge.query.get(id)
        if not badge:
            return jsonify({'error': 'Badge not found'}), 404

        CustomerBadge.query.filter_by(badgeId=id).delete()
        db.session.delete(badge)
        db.session.commit()
        return jsonify({'message': 'Badge deleted', 'badge': badge.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete badge'}), 500


# --- REWARDS ---

@gamification_bp.route('/rewards', methods=['GET'])
def get_rewards():
    try:
        rewards = Reward.query.filter_by(active=True).all()
        return jsonify([r.to_dict() for r in rewards])
    except Exception as e:
        return jsonify({'error': 'Failed to fetch rewards'}), 500

@gamification_bp.route('/rewards', methods=['POST'])
def create_reward():
    data = request.get_json() or {}
    try:
        reward = Reward(
            name=data.get('name'),
            description=data.get('description'),
            pointsRequired=int(data.get('pointsRequired', 0)),
            type=data.get('type', 'NORMAL')
        )
        db.session.add(reward)
        db.session.commit()
        return jsonify(reward.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to create reward'}), 500

@gamification_bp.route('/rewards/<int:id>', methods=['PUT'])
def update_reward(id):
    data = request.get_json() or {}
    try:
        reward = Reward.query.get(id)
        if not reward:
            return jsonify({'error': 'Reward not found'}), 404

        if 'name' in data: reward.name = data['name']
        if 'description' in data: reward.description = data['description']
        if 'pointsRequired' in data: reward.pointsRequired = int(data['pointsRequired'])
        if 'type' in data: reward.type = data['type']

        db.session.commit()
        return jsonify(reward.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update reward'}), 500

@gamification_bp.route('/rewards/<int:id>', methods=['DELETE'])
def delete_reward(id):
    try:
        reward = Reward.query.get(id)
        if not reward:
            return jsonify({'error': 'Reward not found'}), 404

        reward.active = False
        db.session.commit()
        return jsonify({'message': 'Reward deleted (soft)', 'reward': reward.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to delete reward'}), 500


# --- REDEEM & SPIN ---

@gamification_bp.route('/redeem', methods=['POST'])
def redeem_reward():
    data = request.get_json() or {}
    customer_id = data.get('customerId')
    reward_id = data.get('rewardId')

    try:
        customer = Customer.query.get(customer_id)
        reward = Reward.query.get(reward_id)

        if not customer or not reward:
            return jsonify({'error': 'Customer or Reward not found'}), 404
        if not reward.active:
            return jsonify({'error': 'Reward is not active'}), 400
        if customer.points < reward.pointsRequired:
            return jsonify({'error': 'Insufficient points'}), 400

        customer.points -= reward.pointsRequired
        db.session.commit()

        return jsonify({'message': 'Redeem successful', 'customer': customer.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to redeem reward'}), 500


@gamification_bp.route('/spin', methods=['POST'])
def lucky_spin():
    data = request.get_json() or {}
    customer_id = data.get('customerId')
    SPIN_COST = 50

    try:
        customer = Customer.query.get(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        if customer.points < SPIN_COST:
            return jsonify({'error': 'Insufficient points for Lucky Spin'}), 400

        customer.points -= SPIN_COST

        rand = random.random()
        reward_name = ''
        bonus_points = 0
        bonus_xp = 0

        if rand < 0.10:
            reward_name = 'JACKPOT! +200 XP'
            bonus_xp = 200
        elif rand < 0.40:
            reward_name = 'LUCKY! +100 Points'
            bonus_points = 100
        elif rand < 0.80:
            reward_name = 'Balik Modal! +50 Points'
            bonus_points = 50
        else:
            reward_name = 'Zonk! Coba lagi besok.'

        if bonus_points > 0:
            customer.points += bonus_points
        if bonus_xp > 0:
            customer.xp += bonus_xp

        db.session.commit()

        return jsonify({
            'message': 'Spin completed',
            'rewardName': reward_name,
            'bonusPoints': bonus_points,
            'bonusXp': bonus_xp,
            'customer': customer.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to perform lucky spin'}), 500
