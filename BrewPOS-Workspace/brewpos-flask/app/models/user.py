import json
from datetime import datetime
from app.extensions import db

class User(db.Model):
    __tablename__ = 'User'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='CASHIER')  # SUPERADMIN, ADMIN, OWNER, HEADBAR, CASHIER
    assignedShift = db.Column(db.String(50), nullable=True)  # MORNING, NIGHT
    allowedPages = db.Column(db.Text, nullable=True)  # JSON list of paths (e.g. '["/pos", "/inventory"]'), None = default by role
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    expenses = db.relationship('Expense', backref='recordedBy', lazy=True)
    # Shift punya beberapa FK ke User (pembuka/penutup/penjaga), jadi kolomnya eksplisit.
    shifts = db.relationship('Shift', backref='user', lazy=True, foreign_keys='Shift.userId')
    systemLogs = db.relationship('SystemLog', backref='user', lazy=True)

    def get_custom_allowed_pages(self):
        if self.allowedPages:
            try:
                pages = json.loads(self.allowedPages)
                if isinstance(pages, list):
                    return pages
            except Exception:
                return None
        return None

    def to_dict(self):
        custom_pages = self.get_custom_allowed_pages()
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'assignedShift': self.assignedShift,
            'allowedPages': custom_pages,
            'hasCustomAccess': custom_pages is not None,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None
        }
