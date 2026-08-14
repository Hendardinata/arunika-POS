from datetime import datetime
from app.extensions import db

class Transaction(db.Model):
    __tablename__ = 'Transaction'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transactionCode = db.Column(db.String(50), nullable=True)  # e.g. TRX-260814-0001
    subTotal = db.Column(db.Integer, nullable=False, default=0)
    taxAmount = db.Column(db.Integer, nullable=False, default=0)
    parkingFee = db.Column(db.Integer, nullable=False, default=0)
    discountAmount = db.Column(db.Integer, nullable=False, default=0)
    totalAmount = db.Column(db.Integer, nullable=False)
    pointsEarned = db.Column(db.Integer, nullable=False, default=0)
    paymentMethod = db.Column(db.String(50), nullable=False, default='CASH')
    status = db.Column(db.String(50), nullable=False, default='COMPLETED')  # COMPLETED, VOID
    voidReason = db.Column(db.Text, nullable=True)
    voidedAt = db.Column(db.DateTime, nullable=True)
    voidedBy = db.Column(db.Integer, nullable=True)
    customerId = db.Column(db.Integer, db.ForeignKey('Customer.id'), nullable=False)
    shiftId = db.Column(db.Integer, db.ForeignKey('Shift.id'), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    items = db.relationship('TransactionItem', backref='transaction', lazy=True, cascade='all, delete-orphan')

    def get_code(self):
        if self.transactionCode:
            return self.transactionCode
        date_part = self.createdAt.strftime('%Y%m%d') if self.createdAt else datetime.utcnow().strftime('%Y%m%d')
        return f"TR{date_part}{self.id:06d}"

    def to_dict(self, include_items=True, include_customer=True):
        code = self.get_code()
        data = {
            'id': self.id,
            'transactionCode': code,
            'code': code,
            'subTotal': self.subTotal,
            'taxAmount': self.taxAmount,
            'parkingFee': 0,
            'discountAmount': self.discountAmount or 0,
            'totalAmount': self.totalAmount,
            'pointsEarned': self.pointsEarned,
            'paymentMethod': self.paymentMethod,
            'status': self.status,
            'voidReason': self.voidReason,
            'voidedAt': self.voidedAt.isoformat() if self.voidedAt else None,
            'voidedBy': self.voidedBy,
            'customerId': self.customerId,
            'shiftId': self.shiftId,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None
        }
        if include_customer and self.customer:
            data['customer'] = self.customer.to_dict()
        if include_items:
            data['items'] = [item.to_dict() for item in self.items]
        return data


class TransactionItem(db.Model):
    __tablename__ = 'TransactionItem'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    transactionId = db.Column(db.Integer, db.ForeignKey('Transaction.id', ondelete='CASCADE'), nullable=False)
    menuId = db.Column(db.Integer, db.ForeignKey('Menu.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    discountAmount = db.Column(db.Integer, nullable=False, default=0)
    hpp = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'transactionId': self.transactionId,
            'menuId': self.menuId,
            'quantity': self.quantity,
            'price': self.price,
            'discountAmount': self.discountAmount or 0,
            'hpp': self.hpp or 0,
            'menu': self.menu.to_dict(include_category=False) if self.menu else None
        }
