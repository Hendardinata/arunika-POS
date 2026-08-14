from app.extensions import db
from app.models.system_log import SystemLog

def log_activity(action, user_id=None, details=None, entity=None, entity_id=None):
    """
    Log an activity into the SystemLog table.
    """
    try:
        log = SystemLog(
            action=action,
            userId=user_id,
            details=str(details) if details is not None else None,
            entity=entity,
            entityId=entity_id
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"[SystemLogger] Failed to log activity: {e}")
