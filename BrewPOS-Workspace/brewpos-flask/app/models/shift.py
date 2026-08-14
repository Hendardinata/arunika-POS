from datetime import datetime
from app.extensions import db

class Shift(db.Model):
    __tablename__ = 'Shift'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    type = db.Column(db.String(20), nullable=False)  # "MORNING" or "NIGHT"
    startTime = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    endTime = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='OPEN')  # "OPEN" or "CLOSED"
    startingCash = db.Column(db.Integer, nullable=False, default=0)
    endingCash = db.Column(db.Integer, nullable=True)
    expectedEndingCash = db.Column(db.Integer, nullable=True)
    userId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    transactions = db.relationship('Transaction', backref='shift', lazy=True)

    def to_dict(self, include_transactions=False):
        data = {
            'id': self.id,
            'type': self.type,
            'startTime': self.startTime.isoformat() if self.startTime else None,
            'endTime': self.endTime.isoformat() if self.endTime else None,
            'status': self.status,
            'startingCash': self.startingCash,
            'endingCash': self.endingCash,
            'expectedEndingCash': self.expectedEndingCash,
            'userId': self.userId,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None,
            'updatedAt': self.updatedAt.isoformat() if self.updatedAt else None,
            'user': {
                'id': self.user.id,
                'username': self.user.username,
                'role': self.user.role
            } if self.user else None
        }
        if include_transactions:
            data['transactions'] = [t.to_dict(include_items=False, include_customer=False) for t in self.transactions]
        return data
