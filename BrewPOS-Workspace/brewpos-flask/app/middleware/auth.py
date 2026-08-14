from functools import wraps
from flask import request, jsonify, current_app, g
import jwt

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            parts = auth_header.split(' ')
            if len(parts) == 2 and parts[0].lower() == 'bearer':
                token = parts[1]
            elif len(parts) == 1:
                token = parts[0]
                
        if not token:
            return jsonify({'error': 'Unauthorized', 'message': 'Access denied, token missing'}), 401
            
        try:
            secret = current_app.config.get('JWT_SECRET_KEY', 'fallback_secret_for_development_only')
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            g.user = payload
            request.user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Unauthorized', 'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Unauthorized', 'message': 'Invalid token'}), 401
        except Exception as e:
            return jsonify({'error': 'Unauthorized', 'message': str(e)}), 401
            
        return f(*args, **kwargs)
    return decorated
