from datetime import datetime
from app.extensions import db

class InventoryItem(db.Model):
    __tablename__ = 'InventoryItem'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    stock = db.Column(db.Float, nullable=False, default=0.0)
    unit = db.Column(db.String(50), nullable=False, default='pcs')  # pcs, gram, ml, shot, bag, etc.
    minStock = db.Column(db.Float, nullable=False, default=10.0)
    costPerUnit = db.Column(db.Float, nullable=False, default=0.0)  # Purchase cost per 1 unit (gram, ml, pcs)
    imageUrl = db.Column(db.String(500), nullable=True)

    logs = db.relationship('InventoryLog', backref='item', lazy=True, cascade='all, delete-orphan')
    opnameItems = db.relationship('DailyOpnameItem', backref='inventoryItem', lazy=True)

    def to_dict(self):
        # If stock is a whole number, format cleanly or keep float
        stock_val = int(self.stock) if self.stock is not None and self.stock.is_integer() else (self.stock or 0)
        min_stock_val = int(self.minStock) if self.minStock is not None and self.minStock.is_integer() else (self.minStock or 10.0)
        return {
            'id': self.id,
            'name': self.name,
            'stock': stock_val,
            'unit': self.unit,
            'minStock': min_stock_val,
            'costPerUnit': self.costPerUnit or 0.0,
            'imageUrl': self.imageUrl
        }


class InventoryLog(db.Model):
    __tablename__ = 'InventoryLog'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    itemId = db.Column(db.Integer, db.ForeignKey('InventoryItem.id', ondelete='CASCADE'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'IN' or 'OUT'
    totalCost = db.Column(db.Float, nullable=False, default=0.0)
    costPerUnit = db.Column(db.Float, nullable=False, default=0.0)
    supplier = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    receiptUrl = db.Column(db.String(500), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        qty_val = int(self.quantity) if self.quantity is not None and self.quantity.is_integer() else (self.quantity or 0)
        return {
            'id': self.id,
            'itemId': self.itemId,
            'quantity': qty_val,
            'type': self.type,
            'totalCost': self.totalCost or 0.0,
            'costPerUnit': self.costPerUnit or 0.0,
            'supplier': self.supplier,
            'notes': self.notes,
            'receiptUrl': self.receiptUrl,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None
        }


class DailyOpname(db.Model):
    __tablename__ = 'DailyOpname'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='OPEN')  # OPEN, CLOSED
    isStockConfirmed = db.Column(db.Boolean, nullable=False, default=False)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    items = db.relationship('DailyOpnameItem', backref='opname', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'status': self.status,
            'isStockConfirmed': self.isStockConfirmed,
            'items': [item.to_dict() for item in self.items],
            'createdAt': self.createdAt.isoformat() if self.createdAt else None,
            'updatedAt': self.updatedAt.isoformat() if self.updatedAt else None
        }


class DailyOpnameItem(db.Model):
    __tablename__ = 'DailyOpnameItem'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    opnameId = db.Column(db.Integer, db.ForeignKey('DailyOpname.id', ondelete='CASCADE'), nullable=False)
    inventoryItemId = db.Column(db.Integer, db.ForeignKey('InventoryItem.id'), nullable=False)
    openingStock = db.Column(db.Float, nullable=False, default=0.0)
    addedStock = db.Column(db.Float, nullable=False, default=0.0)
    closingStock = db.Column(db.Float, nullable=True)
    used = db.Column(db.Float, nullable=True)
    morningNotes = db.Column(db.Text, nullable=True)
    nightNotes = db.Column(db.Text, nullable=True)

    def to_dict(self):
        def _clean_num(val):
            if val is None:
                return None
            return int(val) if isinstance(val, (int, float)) and float(val).is_integer() else val

        return {
            'id': self.id,
            'opnameId': self.opnameId,
            'inventoryItemId': self.inventoryItemId,
            'openingStock': _clean_num(self.openingStock),
            'addedStock': _clean_num(self.addedStock),
            'closingStock': _clean_num(self.closingStock),
            'used': _clean_num(self.used),
            'morningNotes': self.morningNotes,
            'nightNotes': self.nightNotes,
            'inventoryItem': self.inventoryItem.to_dict() if self.inventoryItem else None
        }
