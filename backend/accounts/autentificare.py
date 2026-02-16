import os
import jwt
import datetime
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from backend.config import get_conn

autentificare_bp = Blueprint('autentificare', __name__)

SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")


@autentificare_bp.route('/api/autentificare', methods=['POST'])
@autentificare_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('parola') or data.get('password')

    if not username or not password:
        return jsonify({'status': 'error', 'message': 'Username și parola sunt obligatorii!'}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # --- SOLUȚIA UNIVERSALĂ ---
        # Folosim SELECT * pentru a nu primi eroare dacă lipsește vreo coloană (ex: password_hash sau nume_complet)
        cur.execute("SELECT * FROM utilizatori WHERE LOWER(username) = LOWER(%s)", (username,))
        user_row = cur.fetchone()

        if user_row:
            # Extragem datele în siguranță folosind .get()
            # Astfel, dacă coloana nu există în DB, primim None în loc de eroare

            # 1. Găsirea parolei (căutăm în ambele coloane posibile)
            stored_pass = user_row.get('password_hash') or user_row.get('parola') or ""

            # 2. Găsirea numelui complet (Fix pentru "UNDEFINED")
            # Dacă nu există nume_complet, folosim username-ul ca să nu apară undefined
            full_name = user_row.get('nume_complet')
            if not full_name or full_name.lower() == 'none':
                full_name = user_row.get('username')

            # 3. Verificarea efectivă a parolei
            pass_ok = False

            # A. Verificare Hash
            try:
                if check_password_hash(stored_pass, password):
                    pass_ok = True
            except:
                pass

                # B. Verificare Text Simplu (pentru baza ta veche)
            if not pass_ok and stored_pass == password:
                pass_ok = True

            if pass_ok:
                # Generare Token
                token = jwt.encode({
                    'user_id': user_row['id'],
                    'username': user_row['username'],
                    'rol': user_row['rol'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
                }, SECRET_KEY, algorithm="HS256")

                print(f"[LOGIN SUCCESS] User: {user_row['username']} | Name: {full_name}")

                # Trimitem datele curate către frontend
                return jsonify({
                    'status': 'success',
                    'token': token,
                    'username': user_row['username'],
                    'nume_complet': full_name,  # Aici va fi sigur un text, nu null/undefined
                    'rol': user_row['rol'],
                    'user_id': user_row['id'],
                    'message': 'Autentificare reușită!'
                }), 200

        return jsonify({'status': 'error', 'message': 'Nume utilizator sau parolă incorecte.'}), 401

    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        return jsonify({'status': 'error', 'message': 'Eroare server la autentificare.'}), 500
    finally:
        if con: con.close()