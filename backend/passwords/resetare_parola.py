import os
from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from email.mime.text import MIMEText
import smtplib

from ..config import get_conn, DB_PATH
from .security import hash_password  # wrapper peste werkzeug.security.generate_password_hash

resetare_bp = Blueprint("resetare", __name__)

# --- Config securitate & email ---
SECRET_KEY = os.getenv("SECRET_KEY", "schimba-asta-in-env!")   # pune în ENV în producție
serializer = URLSafeTimedSerializer(SECRET_KEY)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")  # ex: contul_tău@gmail.com
SMTP_PASS = os.getenv("SMTP_PASS")  # App Password (Gmail, cu 2FA)

# --- helpers ---

def _send_reset_email(to_addr: str, reset_link: str):
    """Trimite e-mailul de resetare. Nu aruncă erori către client."""
    if not (SMTP_USER and SMTP_PASS):
        print("[WARN] Lipsesc SMTP_USER/SMTP_PASS; sar peste trimiterea emailului.")
        return

    body = f"Apasă aici pentru a-ți reseta parola:\n\n{reset_link}"
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = "Resetare parolă - ACS Hwarang"
    msg["From"] = SMTP_USER
    msg["To"] = to_addr

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

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
