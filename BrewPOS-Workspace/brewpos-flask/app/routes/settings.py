from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.system_settings import SystemSettings
from app.services.system_logger import log_activity

settings_bp = Blueprint('settings', __name__, url_prefix='/api/settings')

@settings_bp.route('', methods=['GET'])
def get_settings():
    try:
        settings = SystemSettings.query.all()
        return jsonify([s.to_dict() for s in settings])
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@settings_bp.route('', methods=['POST'])
def update_setting():
    data = request.get_json() or {}
    key = data.get('key')
    value = data.get('value')
    description = data.get('description')

    if not key or value is None:
        return jsonify({'error': 'Key and value are required'}), 400

    try:
        setting = SystemSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
            if description is not None:
                setting.description = description
        else:
            setting = SystemSettings(key=key, value=str(value), description=description)
            db.session.add(setting)

        db.session.commit()

        user_id = request.headers.get('X-User-Id')
        log_activity('UPDATE_SETTINGS', int(user_id) if user_id and user_id.isdigit() else None,
                     f"Updated setting {key} to {value}", 'SystemSettings', setting.id)

        return jsonify(setting.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Internal server error'}), 500
