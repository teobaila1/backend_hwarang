# import os
# import smtplib
# from email.mime.text import MIMEText
# from datetime import datetime
# from textwrap import dedent
# import json
# import ast
#
# # rulează ca modul:  python -m backend.mails.notificare_plati
# from ..config import get_conn, DB_PATH
#
#
# # ---------------- SMTP ----------------
# SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
# SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
# SMTP_USER = os.getenv("SMTP_USER", "baila.teodor@gmail.com")  # ex: "contul_tau@gmail.com"
# SMTP_PASS = os.getenv("SMTP_PASS", "giqozfjtmxzscsri")  # ex: App Password (16 caractere)
# # -------------------------------------
#
#
# def safe_load_children(copii_json):
#     """Parsează în siguranță coloana 'copii' din DB în listă de dict-uri."""
#     if not copii_json:
#         return []
#     # 1) încercăm JSON standard
#     try:
#         return json.loads(copii_json)
#     except Exception:
#         pass
#     # 2) uneori date vechi pot avea formatare tip Python -> încercăm literal_eval
#     try:
#         val = ast.literal_eval(copii_json)
#         if isinstance(val, list):
#             return val
#     except Exception:
#         pass
#     return []
#
#
# def send_email(to_addr: str, subject: str, body: str):
#     if not (SMTP_USER and SMTP_PASS):
#         print("[WARN] Lipsesc SMTP_USER/SMTP_PASS; sar peste trimiterea emailului.")
#         return
#
#     msg = MIMEText(body, _charset="utf-8")
#     msg["Subject"] = subject
#     msg["From"] = SMTP_USER
#     msg["To"] = to_addr
#
#     with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
#         server.starttls()
#         server.login(SMTP_USER, SMTP_PASS)
#         server.send_message(msg)
#
#
# def main():
#     # Trimite doar în ziua 20, exceptând dacă e setat FORCE_SEND=1 pentru test
#     force = os.getenv("FORCE_SEND", "0").strip() == "1"
#     today = datetime.now()
#     if today.day != 20 and not force:
#         print("Nu este 20 ale lunii (și FORCE_SEND nu este 1). Ieșire.")
#         return
#
#     print(f"[BOOT] DB: {DB_PATH}")
#     con = get_conn()
#
#     # părinți cu copii
#     rows = con.execute(
#         "SELECT username, email, copii FROM utilizatori WHERE LOWER(rol) = 'parinte'"
#     ).fetchall()
#
#     total = 0
#     trimise = 0
#
#     for r in rows:
#         username = r["username"]
#         email = r["email"]
#         copii = safe_load_children(r["copii"])
#
#         if not email:
#             continue
#
#         nume_copii = ", ".join(
#             [str(c.get("nume", "")).strip() for c in copii if str(c.get("nume", "")).strip()]
#         ) or "copilul / copiii dvs."
#
#         body = dedent(f"""
#             Bună, {username},
#
#             Vă rugăm să achitați abonamentul lunar pentru: {nume_copii}.
#
#             Termenul recomandat este sfârșitul lunii curente.
#
#             Mulțumim!
#             ACS Hwarang Academy
#         """).strip()
#
#         try:
#             send_email(
#                 to_addr=email,
#                 subject="Notificare plată abonament - ACS Hwarang Academy",
#                 body=body
#             )
#             print(f"[OK] Email trimis către {email}")
#             trimise += 1
#         except Exception as e:
#             print(f"[ERR] Trimitere către {email} a eșuat: {e}")
#
#         total += 1
#
#     print(f"[DONE] {trimise}/{total} emailuri trimise.")
#
#
# if __name__ == "__main__":
#     main()





import os
from flask import Blueprint, request, jsonify
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from ..config import get_conn, DB_PATH
from ..mails.emailer import send_email_http
from ..passwords.security import hash_password

resetare_bp = Blueprint("resetare", __name__)

# --- Config securitate & URL ---
SECRET_KEY = os.getenv("SECRET_KEY", "schimba-asta-in-env!")
serializer = URLSafeTimedSerializer(SECRET_KEY)

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "https://hwarang.ro"
).rstrip("/")


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
    user = con.execute(
        "SELECT id, email FROM utilizatori WHERE LOWER(email) = ?",
        (email,)
    ).fetchone()

    # Nu dezvăluim existența contului → răspuns „success” oricum
    if not user:
        return jsonify({"status": "success", "message": "Dacă emailul există, vei primi un link de resetare."}), 200

    token = serializer.dumps(email, salt="resetare-parola")
    link = f"{FRONTEND_URL}/resetare-parola/{token}"

    subject = "Resetare parolă - ACS Hwarang"
    html = f"""
      <p>Ai cerut resetarea parolei pentru contul tău.</p>
      <p><a href="{link}" target="_blank" rel="noreferrer">Apasă aici pentru a-ți reseta parola</a></p>
      <p>Dacă nu ai cerut tu această acțiune, ignoră acest email.</p>
    """

    # Trimitem prin HTTP (Resend). Nu aruncăm mai departe erorile de rețea.
    send_email_http(email, subject, html)

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
    row = cur.execute(
        "SELECT id FROM utilizatori WHERE LOWER(email) = LOWER(?)",
        (email,)
    ).fetchone()
    if not row:
        return jsonify({"status": "error", "message": "Utilizator inexistent"}), 404

    hashed = hash_password(parola_noua)
    cur.execute(
        "UPDATE utilizatori SET parola = ? WHERE LOWER(email) = LOWER(?)",
        (hashed, email)
    )
    con.commit()

    return jsonify({"status": "success", "message": "Parolă schimbată"}), 200
