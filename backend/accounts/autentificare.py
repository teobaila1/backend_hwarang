import jwt
import datetime
import json
from flask import Blueprint, request, jsonify
from backend.config import get_conn, SECRET_KEY
from backend.passwords.security import check_password

autentificare_bp = Blueprint('autentificare', __name__)


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
        # --- FIX: Cerem coloana 'parola', NU 'password' ---
        cur.execute("""
            SELECT id, username, email, nume_complet, is_placeholder, parola 
            FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
        """, (username_input, username_input))

        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Date de autentificare invalide."}), 401

        # Luăm parola hash-uită din coloana 'parola'
        stored_password = user['parola']

        if stored_password == 'NO_LOGIN_ACCOUNT':
            return jsonify({"status": "error", "message": "Acest cont nu are setată o parolă (este placeholder)."}), 403

        if not check_password(password_input, stored_password):
            return jsonify({"status": "error", "message": "Parolă incorectă."}), 401

        user_id = user['id']
        username_real = user['username']

        # 2. CITIM ROLUL DIN TABELUL NOU 'ROLURI'
        cur.execute("SELECT rol FROM roluri WHERE id_user = %s", (user_id,))
        rol_row = cur.fetchone()

        # Fallback: Dacă nu are rol în tabelul nou, luăm din tabelul vechi (backup)
        if rol_row:
            user_role = rol_row['rol']
        else:
            # Încercăm să citim din tabela veche dacă există coloana rol
            try:
                cur.execute("SELECT rol FROM utilizatori WHERE id = %s", (user_id,))
                user_role = cur.fetchone()['rol']
            except:
                user_role = "Sportiv"  # Default

        # 3. CITIM COPIII DIN TABELUL NOU 'COPII' (Doar dacă e părinte)
        lista_copii = []
        if user_role == 'Parinte':
            # Verificăm dacă există coloana grupa_text sau grupa (pentru compatibilitate)
            try:
                cur.execute("SELECT nume, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))
            except:
                con.rollback()  # În caz că nu există grupa_text, încercăm fără
                cur.execute("SELECT nume, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))

            rows_copii = cur.fetchall()
            for c in rows_copii:
                # Extragem grupa sigur
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
            "copii": lista_copii  # Trimitem lista proaspătă din SQL
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()