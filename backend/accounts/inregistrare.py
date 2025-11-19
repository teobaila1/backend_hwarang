# backend/auth/inregistrare.py  (sau unde îl ai tu în proiect)
import os
import json
from flask import Blueprint, request, jsonify

from ..config import get_conn
from ..passwords.security import hash_password
from ..mails.emailer import send_email_http

inregistrare_bp = Blueprint("inregistrare", __name__)


def trimite_email_confirmare(destinatar: str, username: str):
    subject = "Confirmare creare cont - ACS Hwarang Academy Sibiu"
    text = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont la ACS Hwarang Academy a fost înregistrată cu succes.\n"
        "Te vom contacta după aprobare."
    )
    html = f"""
        <p>Bună, {username}!</p>
        <p>Cererea ta de creare cont la <strong>ACS Hwarang Academy</strong> a fost
        înregistrată cu succes.</p>
        <p>Te vom contacta după aprobare.</p>
    """
    send_email_http(destinatar, subject, html, text)


def trimite_email_acceptare(destinatar: str, username: str):
    subject = "Cerere acceptată - ACS Hwarang Academy"
    text = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont a fost ACCEPTATĂ.\n"
        "Te poți autentifica pe site-ul ACS Hwarang Academy."
    )
    html = f"""
        <p>Bună, {username}!</p>
        <p>Cererea ta de creare cont a fost <strong>ACCEPTATĂ</strong>.</p>
        <p>Te poți autentifica pe site-ul <strong>ACS Hwarang Academy</strong>.</p>
    """
    send_email_http(destinatar, subject, html, text)


def trimite_email_respingere(destinatar: str, username: str):
    subject = "Cerere respinsă - ACS Hwarang Academy"
    text = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont a fost RESPINSĂ.\n"
        "Dacă ai întrebări, te rugăm să ne contactezi."
    )
    html = f"""
        <p>Bună, {username}!</p>
        <p>Cererea ta de creare cont a fost <strong>RESPINSĂ</strong>.</p>
        <p>Dacă ai întrebări, te rugăm să ne contactezi.</p>
    """
    send_email_http(destinatar, subject, html, text)


def _norm_gen(v):
    """Normalizează diverse forme în 'M' / 'F' sau None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"m", "masculin", "male", "b", "boy"}:
        return "M"
    if s in {"f", "feminin", "female", "g", "girl"}:
        return "F"
    return None


@inregistrare_bp.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    full_name = (data.get("nume_complet") or "").strip()
    email = (data.get("email") or "").strip()
    parola = data.get("password") or data.get("parola")
    tip = (data.get("tip") or "").strip()            # "Parinte", "Sportiv", "Antrenor", "AntrenorExtern"
    varsta = data.get("varsta")
    grupe_input = data.get("grupe", None)            # pentru Antrenor / AntrenorExtern
    copii = data.get("copii", [])                    # listă de copii pentru Părinte (opțional)

    # Validări minime
    if not username or not email or not parola or not tip:
        return jsonify({"status": "error", "message": "Toate câmpurile de bază sunt obligatorii"}), 400

    tip_l = tip.lower()
    if tip_l in ("parinte", "sportiv"):
        if varsta is None and tip_l == "sportiv":
            return jsonify({"status": "error", "message": "Vârsta este obligatorie pentru sportiv"}), 400
    elif tip_l == "antrenor":
        if not grupe_input:
            return jsonify({"status": "error", "message": "Grupele sunt obligatorii pentru antrenor"}), 400
    elif tip_l == "antrenorextern":
        pass
    else:
        return jsonify({"status": "error", "message": "Tip de utilizator necunoscut"}), 400

    # Derivă grupe pentru părinte din copii (dacă există); copii sunt OPCIONALI
    grupe = None
    copii_json = None
    if tip_l == "parinte":
        grupe_set = set()
        copii_curati = []
        for c in (copii or []):
            nume_c   = (c.get("nume")  or "").strip()
            grupa_c  = (c.get("grupa") or "").strip()
            varsta_c = c.get("varsta")
            gen_c    = _norm_gen(c.get("gen"))

            # ignoră rânduri complet goale
            if not (nume_c or grupa_c or varsta_c or gen_c):
                continue

            if grupa_c:
                grupe_set.add(grupa_c)

            if isinstance(varsta_c, str) and varsta_c.isdigit():
                varsta_c = int(varsta_c)

            copii_curati.append({
                "nume":   nume_c,
                "grupa":  grupa_c,
                "varsta": varsta_c,
                "gen":    gen_c
            })

        if copii_curati:
            copii_json = json.dumps(copii_curati, ensure_ascii=False)
            grupe = ", ".join(sorted(g for g in grupe_set if g)) or None
        else:
            copii_json = None
            grupe = None
    else:
        copii_json = None
        grupe = (grupe_input or None)

    hashed_parola = hash_password(parola)

    try:
        con = get_conn()
        cur = con.cursor()

        # Unicitate username/email atât în cereri_utilizatori cât și în utilizatori
        cur.execute(
            "SELECT 1 FROM cereri_utilizatori WHERE username = %s LIMIT 1",
            (username,)
        )
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Username deja folosit (în cereri)"}), 409

        cur.execute(
            "SELECT 1 FROM utilizatori WHERE username = %s LIMIT 1",
            (username,)
        )
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Username deja folosit"}), 409

        cur.execute(
            "SELECT 1 FROM cereri_utilizatori WHERE email = %s LIMIT 1",
            (email,)
        )
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Email deja folosit (în cereri)"}), 409

        cur.execute(
            "SELECT 1 FROM utilizatori WHERE email = %s LIMIT 1",
            (email,)
        )
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Email deja folosit"}), 409

        # Inserare cerere (copii/grupe pot fi NULL)
        cur.execute(
            """
            INSERT INTO cereri_utilizatori
                (username, email, parola, tip, varsta, copii, grupe, nume_complet)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (username, email, hashed_parola, tip, varsta, copii_json, grupe, full_name),
        )
        con.commit()

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # Trimitere email după commit (non-blocking)
    try:
        trimite_email_confirmare(email, username)
    except Exception as e:
        print("[WARN] Email confirmare a eșuat:", e)

    return jsonify({"status": "success"}), 200
