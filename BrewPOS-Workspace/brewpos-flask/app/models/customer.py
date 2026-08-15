from datetime import datetime
from app.extensions import db

GUEST_NICKNAME = 'Guest'


def normalize_phone(phone_str):
    """
    Samakan bentuk nomor supaya '+62812-3456', '0812 3456', dan '628123456'
    menunjuk ke satu baris yang sama. Kembalikan None kalau kosong.
    """
    if not phone_str:
        return None
    digits = ''.join(ch for ch in str(phone_str) if ch.isdigit())
    if not digits:
        return None
    if digits.startswith('62'):
        digits = '0' + digits[2:]
    elif not digits.startswith('0'):
        digits = '0' + digits
    return digits


def normalize_email(email_str):
    if not email_str:
        return None
    cleaned = str(email_str).strip().lower()
    return cleaned or None


def mask_phone(phone_str):
    if not phone_str:
        return '-'
    phone_clean = phone_str.strip()
    if len(phone_clean) <= 4:
        return phone_clean
    return '*' * max(0, len(phone_clean) - 4) + phone_clean[-4:]

def mask_email(email_str):
    if not email_str or '@' not in email_str:
        return '-'
    parts = email_str.split('@')
    name_part = parts[0]
    domain_part = parts[1]
    if len(name_part) <= 2:
        masked_name = name_part[0] + '***'
    else:
        masked_name = name_part[:2] + '***'
    return f"{masked_name}@{domain_part}"

class Customer(db.Model):
    __tablename__ = 'Customer'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # Nama panggilan boleh sama; identitas member adalah kontaknya (HP atau email).
    nickname = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    customerType = db.Column(db.String(30), nullable=False, default='REGULAR') # REGULAR (Pelanggan), EMPLOYEE (Karyawan)
    dailyQuota = db.Column(db.Integer, nullable=False, default=0) # Free quota per day for staff/employee
    usedQuotaToday = db.Column(db.Integer, nullable=False, default=0)
    lastQuotaResetDate = db.Column(db.DateTime, nullable=True)
    points = db.Column(db.Integer, nullable=False, default=0)
    pointsExpiryDate = db.Column(db.DateTime, nullable=True)
    xp = db.Column(db.Integer, nullable=False, default=0)
    level = db.Column(db.Integer, nullable=False, default=1)
    lastVisitDate = db.Column(db.DateTime, nullable=True)
    streakCount = db.Column(db.Integer, nullable=False, default=0)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    transactions = db.relationship('Transaction', backref='customer', lazy=True)
    quests = db.relationship('CustomerQuest', backref='customer', lazy=True, cascade='all, delete-orphan')
    badges = db.relationship('CustomerBadge', backref='customer', lazy=True, cascade='all, delete-orphan')

    def check_and_reset_quota(self):
        now = datetime.utcnow()
        if self.lastQuotaResetDate:
            if self.lastQuotaResetDate.date() < now.date():
                self.usedQuotaToday = 0
                self.lastQuotaResetDate = now
        else:
            self.lastQuotaResetDate = now

    def to_dict(self, include_relations=False, user_role=None):
        now = datetime.utcnow()
        used_today = self.usedQuotaToday or 0
        if self.lastQuotaResetDate and self.lastQuotaResetDate.date() < now.date():
            used_today = 0

        daily_q = self.dailyQuota or 0
        remaining_q = max(0, daily_q - used_today) if self.customerType == 'EMPLOYEE' else 0

        # Classification of Member Activity Status (AKTIF vs HILANG)
        days_since_visit = 0
        if self.lastVisitDate:
            days_since_visit = (now - self.lastVisitDate).days
            status_str = 'AKTIF' if days_since_visit <= 30 else 'HILANG'
        else:
            days_since_created = (now - self.createdAt).days if self.createdAt else 0
            days_since_visit = days_since_created
            status_str = 'AKTIF' if days_since_created <= 30 else 'HILANG'

        # Privacy Masking based on User Role (Owner/Admin vs Cashier/Staff)
        is_privileged = user_role in ['OWNER', 'ADMIN']
        display_phone = self.phone if (is_privileged or not self.phone) else mask_phone(self.phone)
        display_email = self.email if (is_privileged or not self.email) else mask_email(self.email)

        # Normalize Type Display: 'PELANGGAN' vs 'KARYAWAN'
        display_type = 'KARYAWAN' if self.customerType == 'EMPLOYEE' else 'PELANGGAN'

        data = {
            'id': self.id,
            'nickname': self.nickname,
            'phone': display_phone or '-',
            'rawPhone': self.phone if is_privileged else None,
            'email': display_email or '-',
            'rawEmail': self.email if is_privileged else None,
            'isMasked': not is_privileged,
            'customerType': self.customerType or 'REGULAR',
            'memberType': display_type,
            'status': status_str, # 'AKTIF' or 'HILANG'
            'daysSinceLastVisit': days_since_visit,
            'dailyQuota': daily_q,
            'usedQuotaToday': used_today,
            'remainingQuota': remaining_q,
            'points': self.points,
            'pointsExpiryDate': self.pointsExpiryDate.isoformat() if self.pointsExpiryDate else None,
            'xp': self.xp,
            'level': self.level,
            'lastVisitDate': self.lastVisitDate.isoformat() if self.lastVisitDate else None,
            'streakCount': self.streakCount,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None,
        }
        if include_relations:
            data['_count'] = {
                'transactions': len(self.transactions)
            }
            data['badges'] = [b.to_dict() for b in self.badges]
            data['quests'] = [q.to_dict() for q in self.quests]
        return data


class CustomerQuest(db.Model):
    __tablename__ = 'CustomerQuest'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customerId = db.Column(db.Integer, db.ForeignKey('Customer.id', ondelete='CASCADE'), nullable=False)
    questId = db.Column(db.Integer, db.ForeignKey('Quest.id', ondelete='CASCADE'), nullable=False)
    progress = db.Column(db.Integer, nullable=False, default=0)
    isCompleted = db.Column(db.Boolean, nullable=False, default=False)
    updatedAt = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('customerId', 'questId', name='uq_customer_quest'),
    )

    quest = db.relationship('Quest', backref='customerQuests', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'customerId': self.customerId,
            'questId': self.questId,
            'progress': self.progress,
            'isCompleted': self.isCompleted,
            'updatedAt': self.updatedAt.isoformat() if self.updatedAt else None,
            'quest': self.quest.to_dict() if self.quest else None
        }


class CustomerBadge(db.Model):
    __tablename__ = 'CustomerBadge'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    customerId = db.Column(db.Integer, db.ForeignKey('Customer.id', ondelete='CASCADE'), nullable=False)
    badgeId = db.Column(db.Integer, db.ForeignKey('Badge.id', ondelete='CASCADE'), nullable=False)
    unlockedAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('customerId', 'badgeId', name='uq_customer_badge'),
    )

    badge = db.relationship('Badge', backref='customerBadges', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'customerId': self.customerId,
            'badgeId': self.badgeId,
            'unlockedAt': self.unlockedAt.isoformat() if self.unlockedAt else None,
            'badge': self.badge.to_dict() if self.badge else None
        }
