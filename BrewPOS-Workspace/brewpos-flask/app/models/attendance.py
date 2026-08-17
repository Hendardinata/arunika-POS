from datetime import datetime
from app.extensions import db


class ShiftHandover(db.Model):
    """Penjaga kasir berganti di tengah sesi tanpa menutup laci kas."""
    __tablename__ = 'ShiftHandover'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    shiftId = db.Column(db.Integer, db.ForeignKey('Shift.id'), nullable=False)
    fromUserId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    toUserId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    note = db.Column(db.String(500), nullable=True)
    # Hitungan laci saat penjaga berganti. Tanpa ini selisih kas hanya diketahui
    # jumlahnya, bukan terjadi di giliran siapa -- dan pada sesi 16 jam yang
    # dijaga bergantian, itu berarti tidak ada yang bisa dimintai keterangan.
    # Boleh kosong: pergantian sebentar (ke belakang, salat) tidak perlu dihitung.
    countedCash = db.Column(db.Integer, nullable=True)
    expectedCash = db.Column(db.Integer, nullable=True)
    difference = db.Column(db.Integer, nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    fromUser = db.relationship('User', foreign_keys=[fromUserId], lazy='joined')
    toUser = db.relationship('User', foreign_keys=[toUserId], lazy='joined')

    def to_dict(self):
        return {
            'id': self.id,
            'shiftId': self.shiftId,
            'fromUserId': self.fromUserId,
            'fromUsername': self.fromUser.username if self.fromUser else None,
            'toUserId': self.toUserId,
            'toUsername': self.toUser.username if self.toUser else None,
            'note': self.note,
            'countedCash': self.countedCash,
            'expectedCash': self.expectedCash,
            'difference': self.difference,
            'createdAt': self.createdAt.isoformat() if self.createdAt else None
        }


class Attendance(db.Model):
    """Jam kerja karyawan. Sengaja terpisah dari Shift: laci kas dan absensi
    menjawab pertanyaan yang berbeda, mencampurnya yang bikin shift lama bingung."""
    __tablename__ = 'Attendance'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    userId = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=False)
    clockIn = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    clockOut = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(500), nullable=True)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', lazy='joined')

    def duration_minutes(self):
        if not self.clockOut:
            return None
        return int((self.clockOut - self.clockIn).total_seconds() // 60)

    def to_dict(self):
        return {
            'id': self.id,
            'userId': self.userId,
            'username': self.user.username if self.user else None,
            'role': self.user.role if self.user else None,
            'clockIn': self.clockIn.isoformat() if self.clockIn else None,
            'clockOut': self.clockOut.isoformat() if self.clockOut else None,
            'durationMinutes': self.duration_minutes(),
            'note': self.note
        }
