from flask import Blueprint, jsonify
from app.models.system_log import SystemLog

logs_bp = Blueprint('logs', __name__, url_prefix='/api/logs')

@logs_bp.route('', methods=['GET'])
def get_logs():
    try:
        logs = SystemLog.query.order_by(SystemLog.createdAt.desc()).limit(200).all()
        return jsonify([l.to_dict() for l in logs])
    except Exception as e:
        print(f"Failed to fetch system logs: {e}")
        return jsonify({'error': 'Failed to fetch system logs'}), 500
