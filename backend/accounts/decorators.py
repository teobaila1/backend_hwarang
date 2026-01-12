# backend/auth/decorators.py
from functools import wraps
from flask import request, jsonify
import jwt
import os

# ATENȚIE: Trebuie să fie aceeași cheie ca în 'autentificare.py'
SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Căutăm token-ul în header-ul "Authorization: Bearer <token>"
        if "Authorization" in request.headers:
            auth_header = request.headers["Authorization"]
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"status": "error", "message": "Token lipsă! Autentifică-te din nou."}), 401

        try:
            # Decodăm token-ul
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            # Salvăm datele utilizatorului în request ca să știm cine e
            request.user_data = data

        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "Sesiune expirată! Loghează-te din nou."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "Token invalid!"}), 401

        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Acest decorator se folosește DUPĂ @token_required
        user_data = getattr(request, "user_data", None)

        if not user_data:
            return jsonify({"status": "error", "message": "Auth lipsă"}), 401

        # Verificăm rolul din token, nu din ce zice userul
        if user_data.get("rol", "").lower() != "admin":
            return jsonify({"status": "error", "message": "Acces interzis! Doar adminii au acces."}), 403

        return f(*args, **kwargs)

    return decorated