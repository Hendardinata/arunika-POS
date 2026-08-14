from app.extensions import db

class Badge(db.Model):
    __tablename__ = 'Badge'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    iconUrl = db.Column(db.String(500), nullable=True)
    requiredTransactions = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'iconUrl': self.iconUrl,
            'requiredTransactions': self.requiredTransactions
        }
