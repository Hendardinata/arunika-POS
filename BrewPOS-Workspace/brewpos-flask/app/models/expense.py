from datetime import datetime
from app.extensions import db

class ExpenseCategory(db.Model):
    __tablename__ = 'ExpenseCategory'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)

    expenses = db.relationship('Expense', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description
        }


class Expense(db.Model):
    __tablename__ = 'Expense'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    amount = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    categoryId = db.Column(db.Integer, db.ForeignKey('ExpenseCategory.id'), nullable=False)
    userId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    receiptUrl = db.Column(db.String(500), nullable=True)
    # CASH_DRAWER = uang diambil dari laci kasir (mengurangi ekspektasi kas saat
    # tutup sesi), OTHER = transfer/rekening pribadi/kartu (tidak menyentuh laci).
    paymentSource = db.Column(db.String(20), nullable=False, default='CASH_DRAWER')
    shiftId = db.Column(db.Integer, db.ForeignKey('Shift.id'), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'amount': self.amount,
            'date': self.date.isoformat() if self.date else None,
            'notes': self.notes,
            'categoryId': self.categoryId,
            'userId': self.userId,
            'receiptUrl': self.receiptUrl,
            'paymentSource': self.paymentSource or 'CASH_DRAWER',
            'paymentSourceLabel': 'Kas Laci' if (self.paymentSource or 'CASH_DRAWER') == 'CASH_DRAWER' else 'Non-Tunai / Luar Kas',
            'shiftId': self.shiftId,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None,
            'updatedAt': self.updatedAt.isoformat() if self.updatedAt else None,
            'category': self.category.to_dict() if self.category else None,
            'recordedBy': {
                'id': self.recordedBy.id,
                'username': self.recordedBy.username,
                'role': self.recordedBy.role
            } if self.recordedBy else None
        }
