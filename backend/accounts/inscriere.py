import os
from flask import Blueprint, request, jsonify

from ..config import get_conn
from ..mails.emailer import send_email_http

inscriere_bp = Blueprint("inscriere", __name__)


def trimite_email_confirmare(destinatar: str, nume: str):
    subject = "Confirmare înscriere - ACS Hwarang Academy Sibiu"
    text = (
        f"Bună, {nume}!\n\n"
        "Îți mulțumim pentru înscrierea la ACS Hwarang Academy.\n"
        "Te vom contacta în cel mai scurt timp!"
    )
    html = f"""
        <p>Bună, {nume}!</p>
        <p>Îți mulțumim pentru înscrierea la <strong>ACS Hwarang Academy</strong>.</p>
        <p>Te vom contacta în cel mai scurt timp!</p>
    """
    send_email_http(destinatar, subject, html, text)


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
            "INSERT INTO inscrieri (nume, prenume, email, telefon, mesaj) VALUES (%s, %s, %s, %s, %s)",
            (nume, prenume, email, telefon, mesaj)
        )
        con.commit()
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # Trimiterea emailului NU blochează răspunsul dacă apar erori la Resend
    try:
        trimite_email_confirmare(email, nume)
    except Exception as e:
        print("[WARN] Eroare la trimiterea emailului de confirmare:", e)

    return jsonify({"status": "success"}), 201
