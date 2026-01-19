import os

import jwt
import datetime
import json
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.passwords.security import check_password

autentificare_bp = Blueprint('autentificare', __name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")
@autentificare_bp.post('/api/login')
def login():
    data = request.get_json(silent=True) or {}
    username_input = (data.get('username') or "").strip()
    password_input = data.get('password')

    if not username_input or not password_input:
        return jsonify({"status": "error", "message": "Username și parola sunt obligatorii!"}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Căutăm utilizatorul (după username sau email)
        cur.execute("""
            SELECT id, username, password, email, nume_complet, is_placeholder, parola 
            FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
        """, (username_input, username_input))

        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Date de autentificare invalide."}), 401

        # Verificăm parola (suportă și coloana veche 'parola' și cea nouă 'password' dacă ai făcut schimbarea,
        # aici folosim 'parola' conform structurii tale vechi)
        stored_password = user['parola']  # sau user['password']

        if stored_password == 'NO_LOGIN_ACCOUNT':
            return jsonify({"status": "error", "message": "Acest cont nu are setată o parolă (este placeholder)."}), 403

        if not check_password(password_input, stored_password):
            return jsonify({"status": "error", "message": "Parolă incorectă."}), 401

        user_id = user['id']
        username_real = user['username']

        # 2. CITIM ROLUL DIN TABELUL NOU 'ROLURI'
        cur.execute("SELECT rol FROM roluri WHERE id_user = %s", (user_id,))
        rol_row = cur.fetchone()

        # Fallback: Dacă nu are rol în tabelul nou, luăm din tabelul vechi (dar ar trebui să aibă)
        if rol_row:
            user_role = rol_row['rol']
        else:
            # Backup
            cur.execute("SELECT rol FROM utilizatori WHERE id = %s", (user_id,))
            user_role = cur.fetchone()['rol']

        # 3. CITIM COPIII DIN TABELUL NOU 'COPII' (Doar dacă e părinte)
        lista_copii = []
        if user_role == 'Parinte':
            cur.execute("SELECT nume, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))
            rows_copii = cur.fetchall()
            for c in rows_copii:
                lista_copii.append({
                    "nume": c['nume'],
                    "grupa": c['grupa_text'],
                    "varsta": str(c['data_nasterii']) if c['data_nasterii'] else ""
                })

        # 4. Generăm Token
        token = jwt.encode({
            'user_id': user_id,
            'username': username_real,
            'rol': user_role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, SECRET_KEY, algorithm="HS256")

        return jsonify({
            "status": "success",
            "token": token,
            "username": username_real,
            "email": user['email'],
            "rol": user_role,
            "nume_complet": user['nume_complet'],
            "is_placeholder": bool(user['is_placeholder']),
            "copii": lista_copii  # Trimitem lista proaspătă din SQL
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()