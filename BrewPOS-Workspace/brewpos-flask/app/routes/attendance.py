from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.attendance import Attendance
from app.middleware.auth import token_required

attendance_bp = Blueprint('attendance', __name__, url_prefix='/api/attendance')


def _open_entry(user_id):
    return Attendance.query.filter_by(userId=user_id, clockOut=None) \
                           .order_by(Attendance.clockIn.desc()).first()


@attendance_bp.route('/clock-in', methods=['POST'])
@token_required
def clock_in():
    data = request.get_json() or {}
    user_id = g.user.get('id')
    try:
        if _open_entry(user_id):
            return jsonify({'error': 'Anda masih tercatat sedang bekerja. Klik Pulang dulu.'}), 400

        entry = Attendance(
            userId=user_id,
            clockIn=datetime.utcnow(),
            note=(data.get('note') or '').strip() or None
        )
        db.session.add(entry)
        db.session.commit()
        return jsonify(entry.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error clocking in: {e}")
        return jsonify({'error': 'Gagal mencatat absen masuk'}), 500


@attendance_bp.route('/clock-out', methods=['POST'])
@token_required
def clock_out():
    data = request.get_json() or {}
    user_id = g.user.get('id')
    try:
        entry = _open_entry(user_id)
        if not entry:
            return jsonify({'error': 'Belum ada absen masuk yang terbuka'}), 404

        entry.clockOut = datetime.utcnow()
        note = (data.get('note') or '').strip()
        if note:
            entry.note = note
        db.session.commit()
        return jsonify(entry.to_dict())
    except Exception as e:
        db.session.rollback()
        print(f"Error clocking out: {e}")
        return jsonify({'error': 'Gagal mencatat absen pulang'}), 500


@attendance_bp.route('/me', methods=['GET'])
@token_required
def my_attendance():
    user_id = g.user.get('id')
    days = int(request.args.get('days', 7))
    try:
        since = datetime.utcnow() - timedelta(days=days)
        entries = Attendance.query.filter(Attendance.userId == user_id, Attendance.clockIn >= since) \
                                  .order_by(Attendance.clockIn.desc()).all()
        current = _open_entry(user_id)
        return jsonify({
            'current': current.to_dict() if current else None,
            'entries': [e.to_dict() for e in entries]
        })
    except Exception as e:
        print(f"Error fetching attendance: {e}")
        return jsonify({'error': 'Gagal memuat absensi'}), 500


@attendance_bp.route('/report', methods=['GET'])
@token_required
def attendance_report():
    """Rekap jam kerja per karyawan untuk periode tertentu."""
    days = request.args.get('days', 'all')
    try:
        query = Attendance.query
        if days and days != 'all':
            try:
                days_int = int(days)
                now = datetime.utcnow()
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                if days_int > 1:
                    start = start - timedelta(days=days_int - 1)
                query = query.filter(Attendance.clockIn >= start)
            except ValueError:
                pass

        entries = query.order_by(Attendance.clockIn.desc()).all()

        summary = {}
        for e in entries:
            name = e.user.username if e.user else f"User #{e.userId}"
            row = summary.setdefault(name, {'username': name, 'sessions': 0, 'minutes': 0, 'openSessions': 0})
            row['sessions'] += 1
            if e.clockOut:
                row['minutes'] += e.duration_minutes() or 0
            else:
                row['openSessions'] += 1

        return jsonify({
            'entries': [e.to_dict() for e in entries],
            'summary': sorted(summary.values(), key=lambda r: r['minutes'], reverse=True)
        })
    except Exception as e:
        print(f"Error building attendance report: {e}")
        return jsonify({'error': 'Gagal memuat rekap absensi'}), 500
