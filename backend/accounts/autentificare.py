import os
import jwt
import datetime
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from backend.config import get_conn

autentificare_bp = Blueprint('autentificare', __name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")


# --- FIX 1: Acceptăm ambele variante de rută (frontend-ul tau pare sa ceara /api/login) ---
@autentificare_bp.route('/api/autentificare', methods=['POST'])
@autentificare_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('parola') or data.get('password')  # Acceptăm și 'password'

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username și parola sunt obligatorii!'}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # Încercarea 1: Structura nouă (cu password_hash)
        try:
            cur.execute("""
                SELECT id, username, password_hash, rol, nume_complet, email 
                FROM utilizatori 
                WHERE LOWER(username) = LOWER(%s)
            """, (username,))
            user = cur.fetchone()
        except Exception as e:
            # Dacă coloana password_hash nu există, PostgreSQL dă eroare.
            # Trebuie să facem ROLLBACK înainte de a încerca altceva!
            con.rollback()
            user = None
            print(f"[LOGIN DEBUG] Nu am gasit structura noua: {e}")

        # Încercarea 2: Structura veche (Fallback pe coloana 'parola')
        if not user:
            try:
                cur = con.cursor()  # Cursor nou după rollback
                cur.execute("""
                    SELECT id, username, parola, rol, nume_complet, email 
                    FROM utilizatori 
                    WHERE LOWER(username) = LOWER(%s)
                """, (username,))
                user_old = cur.fetchone()

                # Adaptăm datele vechi la formatul nou
                if user_old:
                    user = {
                        'id': user_old['id'],
                        'username': user_old['username'],
                        'password_hash': user_old['parola'],  # Punem parola text aici
                        'rol': user_old['rol'],
                        'nume_complet': user_old.get('nume_complet') or user_old['username'],
                        'email': user_old.get('email')
                    }
            except Exception as e2:
                con.rollback()
                print(f"[LOGIN DEBUG] Nici structura veche nu a mers: {e2}")

        # Verificarea Parolei
        if user:
            stored_pass = user.get('password_hash') or user.get('parola') or ""
            pass_ok = False

            # A. Verificare Hash (pentru conturi noi)
            try:
                if check_password_hash(stored_pass, password):
                    pass_ok = True
            except:
                pass

                # B. Verificare Text Simplu (pentru conturi vechi)
            if not pass_ok and stored_pass == password:
                pass_ok = True

            if pass_ok:
                # Generăm Token
                token = jwt.encode({
                    'user_id': user['id'],
                    'username': user['username'],
                    'rol': user['rol'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
                }, SECRET_KEY, algorithm="HS256")

                print(f"[LOGIN SUCCESS] User: {user['username']}")

                return jsonify({
                    'status': 'success',
                    'token': token,
                    'username': user['username'],
                    'nume_complet': user['nume_complet'],  # Rezolvă "undefined"
                    'rol': user['rol'],
                    'user_id': user['id'],
                    'message': 'Autentificare reușită!'
                }), 200

        return jsonify({'status': 'error', 'message': 'Nume utilizator sau parolă incorecte.'}), 401

    except Exception as e:
        print(f"[LOGIN CRITICAL ERROR] {e}")
        return jsonify({'status': 'error', 'message': 'Eroare server la autentificare.'}), 500
    finally:
        if con: con.close()