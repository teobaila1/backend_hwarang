import os
import jwt
from functools import wraps
from flask import request, jsonify

# Folosim aceeași cheie secretă ca în autentificare.py
SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 1. Căutăm token-ul în Header-ul Authorization
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        # Fallback: unii trimit token-ul în x-access-token
        if not token:
            token = request.headers.get('x-access-token')

        if not token:
            return jsonify({'status': 'error', 'message': 'Token lipsă! Autentifică-te din nou.'}), 401

        try:
            # 2. Decodăm Token-ul
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])

            # --- FIXUL ESTE AICI ---
            # Atașăm datele utilizatorului direct de obiectul `request`
            # Astfel, în `parinti.py` poți folosi `request.user_id`
            request.user_id = data['user_id']
            request.user_role = data.get('rol')
            request.user_username = data.get('username')

        except jwt.ExpiredSignatureError:
            return jsonify({'status': 'error', 'message': 'Sesiunea a expirat. Te rugăm să te reloghezi.'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'status': 'error', 'message': 'Token invalid.'}), 401
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 401

        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Verificăm întâi dacă avem token valid (token_required rulează înainte de obicei)
        # Dar pentru siguranță verificăm dacă request.user_role a fost setat
        if not hasattr(request, 'user_role') or not request.user_role:
            return jsonify({'status': 'error', 'message': 'Acces neautorizat. Lipsă rol.'}), 401

        # Verificăm dacă e Admin
        if request.user_role.lower() != 'admin':
            return jsonify({'status': 'error', 'message': 'Acces interzis! Doar administratorii au acces aici.'}), 403

        return f(*args, **kwargs)

    return decorated