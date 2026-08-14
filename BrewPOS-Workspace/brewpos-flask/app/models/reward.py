from app.extensions import db

class Reward(db.Model):
    __tablename__ = 'Reward'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(50), nullable=False, default='NORMAL')  # NORMAL, MYSTERY_BOX, LUCKY_SPIN
    pointsRequired = db.Column(db.Integer, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'pointsRequired': self.pointsRequired,
            'active': self.active
        }
