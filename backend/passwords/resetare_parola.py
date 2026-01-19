import os
from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from backend.config import get_conn
# Importăm funcția de hash care este acum compatibilă cu Werkzeug (fixul anterior)
from backend.passwords.security import hash_password
from backend.mails.emailer import send_email_http

resetare_bp = Blueprint("resetare", __name__)

# --- Configurație ---
SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")
serializer = URLSafeTimedSerializer(SECRET_KEY)

# URL-ul de frontend pentru linkul din email
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://hwarang.ro").rstrip("/")


# 📨 1. CERERE RESETARE (Trimite email)
@resetare_bp.post("/api/reset-password")
def cerere_resetare():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"status": "error", "message": "Email lipsă"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, username FROM utilizatori WHERE LOWER(email) = %s", (email,))
        user = cur.fetchone()

        # Securitate: Nu spunem dacă adresa există sau nu
        if not user:
            return jsonify({"status": "success", "message": "Dacă emailul există, vei primi un link de resetare."}), 200

        # Generăm token valabil 1 oră
        token = serializer.dumps(email, salt="resetare-parola")
        link = f"{FRONTEND_URL}/resetare-parola/{token}"

        username = user['username']
        subject = "Resetare parolă - ACS Hwarang"

        # Conținut HTML pentru email
        html = f"""
          <h3>Salut, {username}!</h3>
          <p>Ai solicitat resetarea parolei pentru contul tău.</p>
          <p>Apasă pe butonul de mai jos pentru a seta o parolă nouă:</p>
          <p>
            <a href="{link}" style="background-color: #d32f2f; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
              Resetează Parola
            </a>
          </p>
          <p><small>Sau copiază acest link în browser: {link}</small></p>
          <p>Link-ul este valabil 1 oră. Dacă nu ai cerut tu asta, ignoră emailul.</p>
        """

        text = f"Salut {username},\n\nPentru a reseta parola, accesează: {link}\n\nLink valabil 1 oră."

        # Trimitem emailul
        try:
            send_email_http(email, subject, html, text)
        except Exception as e:
            print(f"[RESET ERROR] Eșec trimitere email către {email}: {e}")

        return jsonify({"status": "success", "message": "Email trimis. Verifică-ți inbox-ul (și Spam)."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()


# 🛠️ 2. CONFIRMARE RESETARE (Schimbă parola efectiv)
@resetare_bp.post("/api/reset-password/<token>")
def reseteaza_parola(token):
    data = request.get_json(silent=True) or {}
    parola_noua = data.get("password")

    if not parola_noua:
        return jsonify({"status": "error", "message": "Parola lipsește"}), 400

    # Validare Token
    try:
        email = serializer.loads(token, salt="resetare-parola", max_age=3600)  # 1h valabilitate
    except SignatureExpired:
        return jsonify({"status": "error", "message": "Link-ul a expirat. Cere unul nou."}), 400
    except BadSignature:
        return jsonify({"status": "error", "message": "Link invalid."}), 400
    except Exception:
        return jsonify({"status": "error", "message": "Eroare validare link."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # Verificăm utilizatorul
        cur.execute("SELECT id FROM utilizatori WHERE LOWER(email) = %s", (email,))
        row = cur.fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Utilizator inexistent."}), 404

        # --- AICI SE REZOLVĂ PROBLEMA HASH-ULUI ---
        # Folosim noua funcție hash_password din security.py (care folosește werkzeug)
        # Asta va genera un hash compatibil cu check_password_hash
        hashed = hash_password(parola_noua)

        cur.execute(
            "UPDATE utilizatori SET parola = %s WHERE LOWER(email) = %s",
            (hashed, email)
        )
        con.commit()

        return jsonify({"status": "success", "message": "Parola a fost schimbată cu succes. Te poți loga."}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()