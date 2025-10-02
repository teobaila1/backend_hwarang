import json
import os
import ssl
import socket

from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import smtplib
from email.mime.text import MIMEText
from urllib import request as urlrequest

from ..config import get_conn, DB_PATH
from .security import hash_password  # wrapper peste werkzeug.security.generate_password_hash

resetare_bp = Blueprint("resetare", __name__)

# --- Config securitate & email ---
SECRET_KEY = os.getenv("SECRET_KEY", "schimba-asta-in-env!")   # pune în ENV în producție
serializer = URLSafeTimedSerializer(SECRET_KEY)

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://acshwarangacademysibiu.netlify.app")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "baila.teodor@gmail.com")  # ex: "contul_tau@gmail.com"
SMTP_PASS = os.getenv("SMTP_PASS", "giqozfjtmxzscsri")  # ex: App Password (16 caractere)

# --- helpers ---

RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # <- pune cheia aici în Render
FROM_EMAIL     = os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", ""))  # adresa expeditorului

def _send_reset_email(to_addr: str, reset_link: str):
    """
    Încercăm în ordinea: Resend API (HTTP) -> SMTP SSL(465) -> log în consolă.
    NU aruncă excepții mai departe (nu vrem 500 la client dacă eșuează mailul).
    """
    subject = "Resetare parolă - ACS Hwarang"
    body_text = f"Apasă aici pentru a-ți reseta parola:\n\n{reset_link}"
    body_html = f"""
        <p>Apasă aici pentru a-ți reseta parola:</p>
        <p><a href="{reset_link}" target="_blank" rel="noreferrer">{reset_link}</a></p>
    """

    # --- 1) Resend API (preferat pe PaaS) ---
    if RESEND_API_KEY:
        try:
            payload = json.dumps({
                "from": FROM_EMAIL or "no-reply@acshwarang.onresend.com",
                "to": [to_addr],
                "subject": subject,
                "html": body_html
            }).encode("utf-8")

            req = urlrequest.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlrequest.urlopen(req, timeout=10) as resp:
                # 2xx = ok
                print("[MAIL] Resend OK:", resp.status)
                return
        except Exception as e:
            print("[WARN] Resend a eșuat, încerc SMTP:", e)

    # --- 2) SMTP SSL (465) ca fallback ---
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SSL direct
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASS = os.getenv("SMTP_PASS")

    if SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEText(body_html, "html", _charset="utf-8")
            msg["Subject"] = subject
            msg["From"] = FROM_EMAIL or SMTP_USER
            msg["To"] = to_addr

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(msg["From"], [to_addr], msg.as_string())
                print("[MAIL] SMTP SSL OK")
                return
        except (socket.timeout, smtplib.SMTPException, OSError) as e:
            print("[WARN] SMTP a eșuat:", e)

    # --- 3) Fallback: doar logăm linkul (utile pentru test) ---
    print(f"[MAIL-FAKE] către {to_addr}: {reset_link}")

# --- endpoints ---

@resetare_bp.get("/api/test-connection")
def test_connection():
    return jsonify({"status": "success", "message": "Backend is running", "db": str(DB_PATH)}), 200


# 📨 Cerere resetare parolă
@resetare_bp.post("/api/reset-password")
def cerere_resetare():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"status": "error", "message": "Email lipsă"}), 400

    con = get_conn()
    user = con.execute("SELECT id, email FROM utilizatori WHERE LOWER(email) = ?", (email,)).fetchone()
    if not user:
        # Nu dezvăluim existența contului → răspuns „success” oricum
        return jsonify({"status": "success", "message": "Dacă emailul există, vei primi un link de resetare."}), 200

    token = serializer.dumps(email, salt="resetare-parola")
    link = f"{FRONTEND_URL.rstrip('/')}/resetare-parola/{token}"

    try:
        _send_reset_email(email, link)
    except Exception as e:
        print("[WARN] Eroare email reset:", e)

    return jsonify({"status": "success", "message": "Email trimis. Verifică-ți inbox-ul."}), 200


# 🛠️ Schimbă parola cu tokenul
@resetare_bp.post("/api/reset-password/<token>")
def reseteaza_parola(token):
    data = request.get_json(silent=True) or {}
    parola_noua = data.get("password")
    if not parola_noua:
        return jsonify({"status": "error", "message": "Parola lipsește"}), 400

    try:
        email = serializer.loads(token, salt="resetare-parola", max_age=3600)  # 1h
    except SignatureExpired:
        return jsonify({"status": "error", "message": "Token expirat"}), 400
    except BadSignature:
        return jsonify({"status": "error", "message": "Token invalid"}), 400
    except Exception:
        return jsonify({"status": "error", "message": "Token invalid sau expirat"}), 400

    con = get_conn()
    cur = con.cursor()

    # Verifică existența utilizatorului
    row = cur.execute("SELECT id FROM utilizatori WHERE LOWER(email) = LOWER(?)", (email,)).fetchone()
    if not row:
        return jsonify({"status": "error", "message": "Utilizator inexistent"}), 404

    hashed = hash_password(parola_noua)
    cur.execute("UPDATE utilizatori SET parola = ? WHERE LOWER(email) = LOWER(?)", (hashed, email))
    con.commit()

    return jsonify({"status": "success", "message": "Parolă schimbată"}), 200
