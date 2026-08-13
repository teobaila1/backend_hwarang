import os
import jwt
import datetime
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from backend.config import get_conn, SECRET_KEY

autentificare_bp = Blueprint('autentificare', __name__)


@autentificare_bp.route('/api/autentificare', methods=['POST'])
@autentificare_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    # Păstrăm cheia 'username' din frontend, dar valoarea poate fi și email
    username_or_email = data.get('username') 
    password = data.get('parola') or data.get('password')

    if not username_or_email or not password:
        return jsonify({'status': 'error', 'message': 'Username-ul/Email-ul și parola sunt obligatorii!'}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # Căutăm fie după username, fie după email
        query = """
            SELECT * FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(email) = LOWER(%s)
        """
        cur.execute(query, (username_or_email, username_or_email))
        user_row = cur.fetchone()

        if user_row:
            stored_pass = user_row.get('password_hash') or user_row.get('parola') or ""

            full_name = user_row.get('nume_complet')
            if not full_name or full_name.lower() == 'none':
                full_name = user_row.get('username')

            pass_ok = False

            try:
                if check_password_hash(stored_pass, password):
                    pass_ok = True
            except:
                pass

            if not pass_ok and stored_pass == password:
                pass_ok = True

            if pass_ok:
                token = jwt.encode({
                    'user_id': user_row['id'],
                    'username': user_row['username'],
                    'rol': user_row['rol'],
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)
                }, SECRET_KEY, algorithm="HS256")

                print(f"[LOGIN SUCCESS] User: {user_row['username']} | Name: {full_name}")

                return jsonify({
                    'status': 'success',
                    'token': token,
                    'username': user_row['username'],
                    'nume_complet': full_name,
                    'rol': user_row['rol'],
                    'user_id': user_row['id'],
                    'message': 'Autentificare reușită!'
                }), 200

        return jsonify({'status': 'error', 'message': 'Username, email sau parolă incorecte.'}), 401

    except Exception as e:
        print(f"[LOGIN ERROR] {e}")
        return jsonify({'status': 'error', 'message': 'Eroare server la autentificare.'}), 500
    finally:
        if con: con.close()