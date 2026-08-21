from datetime import datetime
from app.extensions import db
from app.waktu import iso_utc

class SystemLog(db.Model):
    __tablename__ = 'SystemLog'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    action = db.Column(db.String(100), nullable=False)
    entity = db.Column(db.String(100), nullable=True)
    entityId = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    userId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'action': self.action,
            'entity': self.entity,
            'entityId': self.entityId,
            'details': self.details,
            'userId': self.userId,
            'createdAt': iso_utc(self.createdAt),
            'user': {
                'username': self.user.username,
                'role': self.user.role
            } if self.user else None
        }
