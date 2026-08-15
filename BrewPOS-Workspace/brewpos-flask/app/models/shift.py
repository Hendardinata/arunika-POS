from datetime import datetime
from app.extensions import db

class Shift(db.Model):
    __tablename__ = 'Shift'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Label sesi, mis. "SESI 1". Baris lama masih menyimpan "MORNING"/"NIGHT".
    type = db.Column(db.String(20), nullable=False)
    sessionNo = db.Column(db.Integer, nullable=True)  # nomor urut sesi dalam satu hari
    startTime = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    endTime = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='OPEN')  # OPEN, CLOSED, NEEDS_REVIEW
    startingCash = db.Column(db.Integer, nullable=False, default=0)
    endingCash = db.Column(db.Integer, nullable=True)
    expectedEndingCash = db.Column(db.Integer, nullable=True)
    closingNote = db.Column(db.Text, nullable=True)
    # userId dipertahankan = pembuka sesi, supaya baris lama tetap terbaca.
    userId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    openedBy = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    closedBy = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    currentUserId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    transactions = db.relationship('Transaction', backref='shift', lazy=True)
    # `user` (pembuka sesi) datang dari backref User.shifts
    openedByUser = db.relationship('User', foreign_keys=[openedBy], lazy='joined')
    closedByUser = db.relationship('User', foreign_keys=[closedBy], lazy='joined')
    currentUser = db.relationship('User', foreign_keys=[currentUserId], lazy='joined')
    handovers = db.relationship(
        'ShiftHandover', backref='shift', lazy=True,
        order_by='ShiftHandover.createdAt'
    )

    def label(self):
        if self.sessionNo:
            return f"SESI {self.sessionNo}"
        # Baris lama: MORNING/NIGHT tetap ditampilkan apa adanya.
        return self.type or 'SESI'

    @staticmethod
    def _user_brief(user):
        if not user:
            return None
        return {'id': user.id, 'username': user.username, 'role': user.role}

    def to_dict(self, include_transactions=False):
        data = {
            'id': self.id,
            'type': self.type,
            'label': self.label(),
            'sessionNo': self.sessionNo,
            'closingNote': self.closingNote,
            'openedBy': self.openedBy,
            'closedBy': self.closedBy,
            'currentUserId': self.currentUserId,
            'openedByUser': self._user_brief(self.openedByUser or self.user),
            'closedByUser': self._user_brief(self.closedByUser),
            'currentUser': self._user_brief(self.currentUser or self.user),
            'handovers': [h.to_dict() for h in self.handovers],
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
