from datetime import datetime
from app.extensions import db

class SystemSettings(db.Model):
    __tablename__ = 'SystemSettings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(255), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, nullable=True)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updatedAt': self.updatedAt.isoformat() if self.updatedAt else None
        }


def get_setting(key, default=None, fallback_key=None):
    """
    Baca satu setelan. Pembacaannya sempat disalin inline di lima tempat,
    termasuk blok fallback TAX_PERCENT -> TAX_PERCENTAGE yang identik di dua
    jalur checkout -- dan yang satu sempat berbeda dari yang lain.

    fallback_key untuk kunci yang pernah berganti nama: dipakai kalau kunci
    utama belum ada, bukan kalau nilainya kosong.
    """
    row = SystemSettings.query.filter_by(key=key).first()
    if row is None and fallback_key:
        row = SystemSettings.query.filter_by(key=fallback_key).first()
    if row is None or row.value is None or str(row.value).strip() == '':
        return default
    return row.value


def get_setting_float(key, default=0.0, fallback_key=None):
    try:
        return float(get_setting(key, None, fallback_key) or default)
    except (TypeError, ValueError):
        return default


def get_setting_int(key, default=0, fallback_key=None):
    try:
        return int(float(get_setting(key, None, fallback_key) or default))
    except (TypeError, ValueError):
        return default
