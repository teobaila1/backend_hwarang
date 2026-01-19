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

        # 1. Căutăm utilizatorul
        cur.execute("""
            SELECT id, username, email, nume_complet, is_placeholder, parola 
            FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
        """, (username_input, username_input))

        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Utilizatorul nu există."}), 401

        # --- FIX SUPREM PENTRU PAROLĂ ---
        raw_pass = user['parola']
        stored_password = ""

        if raw_pass:
            # Convertim orice ar fi în string
            if isinstance(raw_pass, bytes):
                stored_password = raw_pass.decode('utf-8').strip()
            else:
                stored_password = str(raw_pass).strip()

            # ELIMINĂM ARTEFACTELE PYTHON (b'...')
            # Aceasta este linia care repară parolele vechi
            if stored_password.startswith("b'") and stored_password.endswith("'"):
                stored_password = stored_password[2:-1]
            elif stored_password.startswith('b"') and stored_password.endswith('"'):
                stored_password = stored_password[2:-1]

        if stored_password == 'NO_LOGIN_ACCOUNT':
            return jsonify({"status": "error", "message": "Acest cont este placeholder."}), 403

        # --- VERIFICARE ---
        is_valid = False

        # A. Metoda Hash (Normală)
        try:
            if check_password(password_input, stored_password):
                is_valid = True
        except Exception:
            pass

        # B. Metoda Fallback (Text Simplu) - Doar dacă A eșuează
        if not is_valid:
            if stored_password == password_input:
                is_valid = True

        if not is_valid:
            print(f"[LOGIN FAIL] User: {username_input} | Hash curatat: {stored_password}")
            return jsonify({"status": "error", "message": "Parolă incorectă."}), 401

        # --- LOGIN REUȘIT: Preluăm datele ---
        user_id = user['id']
        username_real = user['username']

        # Citim Rolul
        cur.execute("SELECT rol FROM roluri WHERE id_user = %s", (user_id,))
        rol_row = cur.fetchone()
        if rol_row:
            user_role = rol_row['rol']
        else:
            try:
                cur.execute("SELECT rol FROM utilizatori WHERE id = %s", (user_id,))
                res = cur.fetchone()
                user_role = res['rol'] if res else "Sportiv"
            except:
                user_role = "Sportiv"

        # Citim Copiii (Dacă e părinte)
        lista_copii = []
        if user_role == 'Parinte':
            try:
                cur.execute("SELECT nume, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))
            except:
                con.rollback()
                cur.execute("SELECT nume, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))

            rows_copii = cur.fetchall()
            for c in rows_copii:
                grp = c.get('grupa_text') or c.get('grupa') or ""
                dob = str(c['data_nasterii']) if c.get('data_nasterii') else ""
                lista_copii.append({"nume": c['nume'], "grupa": grp, "varsta": dob})

        # Generăm Token
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
            "copii": lista_copii
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()