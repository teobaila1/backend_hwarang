import os
import smtplib
from email.mime.text import MIMEText
from flask import Blueprint, request, jsonify

from ..config import get_conn, DB_PATH  # o singură sursă pentru DB

inscriere_bp = Blueprint("inscriere", __name__)

# ---- Config SMTP din variabile de mediu (nu hardcoda parole!) ----
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")  # ex: contul_tău@gmail.com
SMTP_PASS = os.getenv("SMTP_PASS")  # App Password (16 caractere la Gmail)

def _trimite_email(to_addr: str, subject: str, body: str):
    if not (SMTP_USER and SMTP_PASS):
        print("[WARN] Lipsesc SMTP_USER/SMTP_PASS; sar peste trimiterea emailului.")
        return
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = to_addr
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

def trimite_email_confirmare(destinatar: str, nume: str):
    body = (
        f"Bună, {nume}!\n\n"
        "Îți mulțumim pentru înscrierea la ACS Hwarang Academy.\n"
        "Te vom contacta în cel mai scurt timp!"
    )
    _trimite_email(destinatar, "Confirmare înscriere - ACS Hwarang Academy Sibiu", body)
# ------------------------------------------------------------------

@inscriere_bp.post("/api/inscriere")
def inscriere():
    data = request.get_json(silent=True) or {}
    nume = (data.get("name") or "").strip()
    prenume = (data.get("prename") or "").strip()
    email = (data.get("email") or "").strip()
    telefon = (data.get("phone") or "").strip()
    mesaj = (data.get("message") or "").strip()

    if not nume or not email or not telefon:
        return jsonify({"status": "error", "message": "Câmpuri obligatorii lipsă"}), 400

    try:
        con = get_conn()
        con.execute(
            "INSERT INTO inscrieri (nume, prenume, email, telefon, mesaj) VALUES (?, ?, ?, ?, ?)",
            (nume, prenume, email, telefon, mesaj)
        )
        con.commit()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # Trimiterea emailului NU blochează răspunsul dacă SMTP nu e configurat corect
    try:
        trimite_email_confirmare(email, nume)
    except Exception as e:
        print("[WARN] Eroare la trimiterea emailului de confirmare:", e)

    return jsonify({"status": "success"}), 201
