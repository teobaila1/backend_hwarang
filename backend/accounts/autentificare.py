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
        # IMPORTANT: Cerem coloana 'parola' (vechea denumire din baza ta)
        cur.execute("""
            SELECT id, username, email, nume_complet, is_placeholder, parola 
            FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
        """, (username_input, username_input))

        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Utilizatorul nu există."}), 401

        # --- FIX ROBUST PENTRU CITIREA PAROLEI ---
        raw_pass = user['parola']
        stored_password = ""

        if raw_pass:
            if isinstance(raw_pass, bytes):
                # Cazul 1: Baza de date returnează bytes (ex: b'$2b$...')
                # Trebuie decodat în string UTF-8
                stored_password = raw_pass.decode('utf-8').strip()
            else:
                # Cazul 2: Baza de date returnează string (ex: '$2b$...')
                # Doar curățăm spațiile
                stored_password = str(raw_pass).strip()

        # ----------------------------------------

        if stored_password == 'NO_LOGIN_ACCOUNT':
            return jsonify({"status": "error", "message": "Acest cont nu are setată o parolă (este placeholder)."}), 403

        # Verificăm parola
        is_valid = False
        try:
            # check_password ar trebui să primească (parola_in_clar, hash_ul_din_db)
            is_valid = check_password(password_input, stored_password)
        except Exception as e:
            print(f"[LOGIN ERROR] Eroare verificare hash: {e}")
            is_valid = False

        if not is_valid:
            # Debugging: Ajută să vezi în logs ce compară (doar hash-ul, nu parola clară)
            print(f"[LOGIN FAIL] Input User: {username_input}")
            print(f"[LOGIN FAIL] Hash DB (final): '{stored_password}'")
            return jsonify({"status": "error", "message": "Parolă incorectă."}), 401

        # --- DACA PAROLA E OK, PRELUĂM DATELE ---
        user_id = user['id']
        username_real = user['username']

        # 2. CITIM ROLUL
        cur.execute("SELECT rol FROM roluri WHERE id_user = %s", (user_id,))
        rol_row = cur.fetchone()

        if rol_row:
            user_role = rol_row['rol']
        else:
            # Fallback la tabelul vechi
            try:
                cur.execute("SELECT rol FROM utilizatori WHERE id = %s", (user_id,))
                res = cur.fetchone()
                user_role = res['rol'] if res else "Sportiv"
            except:
                user_role = "Sportiv"

        # 3. CITIM COPIII (Doar dacă e părinte)
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
        if con: con.close()