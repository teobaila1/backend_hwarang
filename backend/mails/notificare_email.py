import os
import resend  # <--- IMPORT NOU
from threading import Thread  # <--- IMPORT VITEZĂ
from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..config import get_conn
from ..passwords.security import hash_password

# Definim blueprint-ul
resetare_bp = Blueprint("resetare", __name__)

# Configurare Resend
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_IDENTITY = "ACS Hwarang Sibiu <site@hwarang.ro>"

# Configurare Securitate
SECRET_KEY = os.environ.get("SECRET_KEY", "schimba-asta-in-env!")
serializer = URLSafeTimedSerializer(SECRET_KEY)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://hwarang.ro").rstrip("/")


# --- FUNCȚIE TRIMITERE RESET ---
def trimite_email_reset(destinatar, link_resetare):
    try:
        if not resend.api_key:
            print("[MAIL RESET] Lipseste API KEY")
            return

        html = f"""
        <div style="font-family: Arial; padding: 20px; border: 1px solid #ddd;">
            <h2 style="color: #d32f2f;">Resetare Parolă</h2>
            <p>Ai solicitat resetarea parolei pentru contul tău Hwarang.</p>
            <p>Click pe butonul de mai jos pentru a continua:</p>
            <a href="{link_resetare}" 
               style="background: #d32f2f; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
               Resetează Parola
            </a>
            <p><small>Link-ul expiră într-o oră.</small></p>
        </div>
        """

        resend.Emails.send({
            "from": SENDER_IDENTITY,
            "to": destinatar,
            "subject": "Resetare parolă - ACS Hwarang",
            "html": html
        })
        print(f"[MAIL RESET] Trimis la {destinatar}")
    except Exception as e:
        print(f"[MAIL RESET ERROR] {e}")


# --- RUTE ---

@resetare_bp.post("/api/reset-password")
def cerere_resetare():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"status": "error", "message": "Email lipsă"}), 400

    # Verificăm dacă userul există
    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("SELECT id FROM utilizatori WHERE LOWER(email) = %s", (email,))
        user = cur.fetchone()

        # Dacă userul există, generăm token și trimitem mail
        if user:
            token = serializer.dumps(email, salt="resetare-parola")
            link = f"{FRONTEND_URL}/resetare-parola/{token}"

            # Trimitem în fundal
            Thread(target=trimite_email_reset, args=(email, link)).start()

    except Exception as e:
        print(f"[RESET ERROR] {e}")

    # Răspundem SUCCESS oricum (Security best practice - să nu ghicească hackerii emailuri)
    return jsonify({"status": "success", "message": "Dacă emailul există, vei primi instrucțiuni."}), 200


@resetare_bp.post("/api/reset-password/<token>")
def reseteaza_parola(token):
    data = request.get_json(silent=True) or {}
    parola_noua = data.get("password")

    if not parola_noua:
        return jsonify({"status": "error", "message": "Parola lipsește"}), 400

    try:
        email = serializer.loads(token, salt="resetare-parola", max_age=3600)  # 1h valabilitate
    except SignatureExpired:
        return jsonify({"status": "error", "message": "Link expirat. Cere altul."}), 400
    except BadSignature:
        return jsonify({"status": "error", "message": "Link invalid."}), 400
    except Exception:
        return jsonify({"status": "error", "message": "Eroare token."}), 400

    # Schimbarea parolei în DB
    con = get_conn()
    try:
        hashed = hash_password(parola_noua)
        cur = con.cursor()
        cur.execute("UPDATE utilizatori SET parola = %s WHERE LOWER(email) = %s", (hashed, email))
        con.commit()

        return jsonify({"status": "success", "message": "Parola a fost schimbată!"}), 200
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()