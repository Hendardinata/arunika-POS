from app.extensions import db

class Quest(db.Model):
    __tablename__ = 'Quest'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(50), nullable=False, default='TOTAL_TRANSACTIONS')  # TOTAL_TRANSACTIONS, TOTAL_SPEND, BUY_ITEM
    targetEntityId = db.Column(db.Integer, nullable=True)  # menuId for BUY_ITEM
    targetValue = db.Column(db.Integer, nullable=False)
    rewardPoints = db.Column(db.Integer, nullable=False, default=0)
    rewardXp = db.Column(db.Integer, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)
    isDaily = db.Column(db.Boolean, nullable=False, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'targetEntityId': self.targetEntityId,
            'targetValue': self.targetValue,
            'rewardPoints': self.rewardPoints,
            'rewardXp': self.rewardXp,
            'active': self.active,
            'isDaily': self.isDaily
        }
