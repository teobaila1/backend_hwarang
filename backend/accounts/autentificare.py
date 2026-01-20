import os
import jwt
import datetime
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from backend.config import get_conn

autentificare_bp = Blueprint('autentificare', __name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")


@autentificare_bp.post('/api/autentificare')
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('parola')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username și parola sunt obligatorii!'}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        # Căutăm utilizatorul (case-insensitive la username)
        cur.execute("""
            SELECT id, username, password_hash, rol, nume_complet, email 
            FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s)
        """, (username,))
        user = cur.fetchone()

        # Verificăm parola (suportăm și parole vechi text-clar, și hash-uri noi)
        if user:
            stored_pass = user['password_hash'] or ""  # Uneori coloana e password sau parola
            pass_ok = False

            # 1. Încercăm verificare hash
            try:
                if check_password_hash(stored_pass, password):
                    pass_ok = True
            except:
                pass  # Nu e hash valid

            # 2. Dacă nu e hash, verificăm text simplu (pentru conturi vechi/importate)
            if not pass_ok and stored_pass == password:
                pass_ok = True

            if pass_ok:
                # Generăm Token-ul
                token = jwt.encode({
                    'user_id': user['id'],
                    'username': user['username'],
                    'rol': user['rol'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
                }, SECRET_KEY, algorithm="HS256")

                # --- AICI ESTE FIX-UL PENTRU UNDEFINED ---
                # Trimitem TOATE datele pe care le-ar putea căuta frontend-ul
                return jsonify({
                    'status': 'success',
                    'token': token,
                    'username': user['username'],  # Frontend-ul caută asta
                    'nume_complet': user['nume_complet'],  # Sau asta
                    'rol': user['rol'],
                    'user_id': user['id'],
                    'message': 'Autentificare reușită!'
                }), 200

        return jsonify({'status': 'error', 'message': 'Nume utilizator sau parolă incorecte.'}), 401

    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        # Fallback pentru coloana parola vs password_hash dacă ai structura veche
        try:
            # Încercare disperată pe coloana veche 'parola'
            cur.execute("SELECT id, username, parola, rol FROM utilizatori WHERE username=%s", (username,))
            u_old = cur.fetchone()
            if u_old and u_old['parola'] == password:
                token = jwt.encode({'user_id': u_old['id'], 'rol': u_old['rol']}, SECRET_KEY, algorithm="HS256")
                return jsonify(
                    {'status': 'success', 'token': token, 'username': u_old['username'], 'rol': u_old['rol']}), 200
        except:
            pass

        return jsonify({'status': 'error', 'message': 'Eroare server.'}), 500
    finally:
        if con: con.close()