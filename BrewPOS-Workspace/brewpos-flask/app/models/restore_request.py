from datetime import datetime

from app.extensions import db
from app.waktu import iso_utc

# Permintaan menganggur dibuang setelah sejauh ini. Berkas unggahan yang
# menunggu persetujuan berisi seluruh basis data; ia tidak boleh menunggu
# selamanya kalau ternyata tidak jadi.
UMUR_JAM = 24


class RestoreRequest(db.Model):
    """
    Permintaan pemulihan basis data yang menunggu keputusan Superadmin.

    Restore menimpa seluruh isi toko dan tidak bisa dibatalkan, jadi tindakannya
    dipecah dua: Admin/Owner MENGAJUKAN, Superadmin MEMUTUSKAN. Keduanya
    dilakukan sambil masuk sebagai dirinya sendiri, jadi tidak ada sandi yang
    berpindah tangan dan jejaknya menyebut dua nama yang berbeda.
    """
    __tablename__ = 'RestoreRequest'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    requestedBy = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    # 'HISTORY' = berkas yang sudah ada di riwayat server.
    # 'UPLOAD'  = berkas yang diunggah pemohon, menunggu di folder cadangan.
    sourceType = db.Column(db.String(20), nullable=False, default='HISTORY')
    filename = db.Column(db.String(255), nullable=False)   # nama untuk dibaca manusia
    storedName = db.Column(db.String(255), nullable=False)  # nama berkas di folder cadangan
    reason = db.Column(db.Text, nullable=True)

    # PENDING -> APPROVED | REJECTED | CANCELLED | FAILED
    status = db.Column(db.String(20), nullable=False, default='PENDING')
    decidedBy = db.Column(db.Integer, db.ForeignKey('User.id'), nullable=True)
    decidedAt = db.Column(db.DateTime, nullable=True)
    decisionNote = db.Column(db.Text, nullable=True)

    createdAt = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    pemohon = db.relationship('User', foreign_keys=[requestedBy])
    pemutus = db.relationship('User', foreign_keys=[decidedBy])

    def to_dict(self):
        return {
            'id': self.id,
            'sourceType': self.sourceType,
            'filename': self.filename,
            'reason': self.reason,
            'status': self.status,
            'requestedBy': self.pemohon.username if self.pemohon else None,
            'decidedBy': self.pemutus.username if self.pemutus else None,
            'decisionNote': self.decisionNote,
            'createdAt': iso_utc(self.createdAt),
            'decidedAt': iso_utc(self.decidedAt) if self.decidedAt else None,
        }
