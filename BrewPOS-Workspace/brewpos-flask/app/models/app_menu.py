from app.extensions import db

class AppMenu(db.Model):
    __tablename__ = 'AppMenu'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(500), nullable=False)
    icon = db.Column(db.String(100), nullable=True)

    roleAccess = db.relationship('RoleAccess', backref='appMenu', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'icon': self.icon
        }


class RoleAccess(db.Model):
    __tablename__ = 'RoleAccess'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    role = db.Column(db.String(50), nullable=False)  # "ADMIN", "HEADBAR", "CASHIER", "OWNER"
    appMenuId = db.Column(db.Integer, db.ForeignKey('AppMenu.id', ondelete='CASCADE'), nullable=False)
    canView = db.Column(db.Boolean, nullable=False, default=True)
    canEdit = db.Column(db.Boolean, nullable=False, default=False)

    __table_args__ = (
        db.UniqueConstraint('role', 'appMenuId', name='uq_role_app_menu'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'appMenuId': self.appMenuId,
            'canView': self.canView,
            'canEdit': self.canEdit,
            'appMenu': self.appMenu.to_dict() if self.appMenu else None
        }
