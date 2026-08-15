from app.extensions import db

class Menu(db.Model):
    __tablename__ = 'Menu'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False)
    hpp = db.Column(db.Integer, nullable=False, default=0)
    imageUrl = db.Column(db.String(500), nullable=True)
    categoryId = db.Column(db.Integer, db.ForeignKey('Category.id'), nullable=False)
    recipeNotes = db.Column(db.Text, nullable=True)
    # Menu yang sudah pernah terjual tidak boleh dihapus; nonaktifkan supaya
    # hilang dari POS tapi riwayat penjualan & laporan HPP tetap utuh.
    isActive = db.Column(db.Boolean, nullable=False, default=True)

    transactionItems = db.relationship('TransactionItem', backref='menu', lazy=True)
    recipeIngredients = db.relationship('RecipeIngredient', backref='menu', lazy=True, cascade='all, delete-orphan')

    def get_code(self):
        cat_code = 'MN'
        if self.category and self.category.name:
            c_name = self.category.name.upper()
            if 'KOPI' in c_name or 'COFFEE' in c_name: cat_code = 'CF'
            elif 'MAKAN' in c_name or 'FOOD' in c_name: cat_code = 'FD'
            elif 'TEH' in c_name or 'TEA' in c_name: cat_code = 'TE'
            elif 'NON' in c_name or 'BEV' in c_name: cat_code = 'BV'
            else:
                clean = ''.join(c for c in c_name if c.isalnum())[:2]
                cat_code = clean if clean else 'MN'
        return f"{cat_code}{self.id:04d}"

    def to_dict(self, include_category=True, sold_count=0):
        data = {
            'id': self.id,
            'code': self.get_code(),
            'menuCode': self.get_code(),
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'hpp': self.hpp,
            'imageUrl': self.imageUrl,
            'categoryId': self.categoryId,
            'recipeNotes': self.recipeNotes,
            'isActive': bool(self.isActive) if self.isActive is not None else True,
            'soldCount': sold_count
        }
        if include_category and self.category:
            data['category'] = self.category.to_dict()
        return data


class RecipeIngredient(db.Model):
    __tablename__ = 'RecipeIngredient'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    menuId = db.Column(db.Integer, db.ForeignKey('Menu.id', ondelete='CASCADE'), nullable=False)
    inventoryItemId = db.Column(db.Integer, db.ForeignKey('InventoryItem.id'), nullable=False)
    quantityNeeded = db.Column(db.Float, nullable=False)  # Qty needed per 1 serving (e.g. 18.0 g)

    __table_args__ = (
        db.UniqueConstraint('menuId', 'inventoryItemId', name='uq_menu_inventory_ingredient'),
    )

    inventoryItem = db.relationship('InventoryItem', backref='usedInRecipes', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'menuId': self.menuId,
            'inventoryItemId': self.inventoryItemId,
            'quantityNeeded': self.quantityNeeded,
            'inventoryItem': self.inventoryItem.to_dict() if self.inventoryItem else None
        }
