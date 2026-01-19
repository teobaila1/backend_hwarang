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
        # Cerem coloana 'parola' (vechea denumire)
        cur.execute("""
            SELECT id, username, email, nume_complet, is_placeholder, parola 
            FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
        """, (username_input, username_input))

        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Utilizatorul nu există."}), 401

        # --- FIX ROBUST PENTRU PAROLĂ ---
        raw_pass = user['parola']

        # 1. Convertim la string și ștergem spațiile goale (pentru compatibilitate CHAR/VARCHAR)
        stored_password = str(raw_pass).strip() if raw_pass else ""

        # DEBUG: Poți vedea asta în Render Logs dacă tot nu merge
        print(f"[LOGIN DEBUG] User: {username_input} | Hash din DB: {stored_password[:10]}...")

        if stored_password == 'NO_LOGIN_ACCOUNT':
            return jsonify({"status": "error", "message": "Acest cont nu are setată o parolă (este placeholder)."}), 403

        # Verificăm parola
        try:
            is_valid = check_password(password_input, stored_password)
        except Exception as e:
            print(f"[LOGIN ERROR] Eroare la check_password: {e}")
            is_valid = False

        if not is_valid:
            return jsonify({"status": "error", "message": "Parolă incorectă."}), 401

        # --- PRELUARE DATE SUPLIMENTARE ---
        user_id = user['id']
        username_real = user['username']

        # 2. CITIM ROLUL DIN TABELUL NOU 'ROLURI'
        cur.execute("SELECT rol FROM roluri WHERE id_user = %s", (user_id,))
        rol_row = cur.fetchone()

        if rol_row:
            user_role = rol_row['rol']
        else:
            # Fallback la tabelul vechi dacă nu are rol în cel nou
            try:
                cur.execute("SELECT rol FROM utilizatori WHERE id = %s", (user_id,))
                res = cur.fetchone()
                user_role = res['rol'] if res else "Sportiv"
            except:
                user_role = "Sportiv"

        # 3. CITIM COPIII DIN TABELUL NOU 'COPII' (Doar dacă e părinte)
        lista_copii = []
        if user_role == 'Parinte':
            try:
                # Încercăm să citim și grupa_text
                cur.execute("SELECT nume, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))
            except:
                con.rollback()
                # Fallback dacă nu există grupa_text
                cur.execute("SELECT nume, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))

            rows_copii = cur.fetchall()
            for c in rows_copii:
                grp = c.get('grupa_text') or c.get('grupa') or ""
                lista_copii.append({
                    "nume": c['nume'],
                    "grupa": grp,
                    "varsta": str(c['data_nasterii']) if c.get('data_nasterii') else ""
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
            "copii": lista_copii
        }), 200

    except Exception as e:
        print(f"[LOGIN CRASH] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()