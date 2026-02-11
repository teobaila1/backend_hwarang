import os
import resend  # <--- IMPORT NOU
from threading import Thread  # <--- IMPORT PENTRU VITEZĂ
from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from backend.config import get_conn
from backend.passwords.security import hash_password

# --- ELIMINĂM IMPORTUL VECHI CARE DĂDEA EROARE ---
# from backend.mails.emailer import send_email_http

resetare_bp = Blueprint("resetare", __name__)

# --- CONFIGURARE RESEND ---
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_IDENTITY = "ACS Hwarang Sibiu <site@hwarang.ro>"

# --- CONFIGURARE SECURITATE ---
SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")
serializer = URLSafeTimedSerializer(SECRET_KEY)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://hwarang.ro").rstrip("/")


# --- FUNCȚIE HELPER PENTRU TRIMITERE ASINCRONĂ ---
def _send_reset_email_async(destinatar, username, link):
    try:
        if not resend.api_key:
            print("[RESET ERROR] Lipseste RESEND_API_KEY")
            return

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
          <h2 style="color: #d32f2f;">Resetare Parolă</h2>
          <p>Salut, <strong>{username}</strong>!</p>
          <p>Ai solicitat resetarea parolei pentru contul tău ACS Hwarang.</p>
          <p>Apasă pe butonul de mai jos pentru a seta o parolă nouă:</p>

          <div style="text-align: center; margin: 30px 0;">
              <a href="{link}" style="background-color: #d32f2f; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                Resetează Parola
              </a>
          </div>

          <p><small>Link-ul este valabil timp de 1 oră.</small></p>
          <hr style="border: 0; border-top: 1px solid #eee;">
          <p style="color: #888; font-size: 12px;">Dacă nu ai solicitat acest email, te rugăm să îl ignori.</p>
        </div>
        """

        resend.Emails.send({
            "from": SENDER_IDENTITY,
            "to": destinatar,
            "subject": "Resetare parolă - ACS Hwarang",
            "html": html_content
        })
    except Exception as e:
        print(f"[RESET ERROR] Resend a esuat: {e}")


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

        if user:
            username = user['username']
            token = serializer.dumps(email, salt="resetare-parola")
            link = f"{FRONTEND_URL}/resetare-parola/{token}"
            Thread(target=_send_reset_email_async, args=(email, username, link)).start()

    except Exception as e:
        print(f"[RESET DB ERROR] {e}")
    finally:
        if con: con.close()

    return jsonify({"status": "success", "message": "Dacă emailul există, vei primi instrucțiuni."}), 200


@resetare_bp.post("/api/reset-password/<token>")
def reseteaza_parola(token):
    # 1. Validări de bază
    data = request.get_json(silent=True) or {}
    parola_noua = data.get("password")

    if not parola_noua:
        return jsonify({"status": "error", "message": "Parola lipsește"}), 400

    try:
        email = serializer.loads(token, salt="resetare-parola", max_age=3600)
    except Exception:
        return jsonify({"status": "error", "message": "Link invalid sau expirat."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 2. Verificăm dacă userul există
        cur.execute("SELECT id FROM utilizatori WHERE LOWER(email) = %s", (email,))
        row = cur.fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Utilizator inexistent."}), 404

        # 3. Generăm hash-ul
        hashed = hash_password(parola_noua)

        # 4. UPDATE SIMPLU (Doar coloana care există!)
        cur.execute("""
            UPDATE utilizatori 
            SET parola = %s 
            WHERE LOWER(email) = %s
        """, (hashed, email))

        con.commit()
        return jsonify({"status": "success", "message": "Parola a fost schimbată!"}), 200

    except Exception as e:
        if con: con.rollback()
        print(f"[RESET ERROR] {e}")
        return jsonify({"status": "error", "message": "Eroare server."}), 500
    finally:
        if con: con.close()