# backend/auth/inregistrare.py  (sau unde îl ai tu în proiect)
import os
import json
from datetime import datetime

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
    tip = (data.get("tip") or "").strip()

    # Câmp nou: Data Nașterii
    data_nasterii = data.get("data_nasterii")

    grupe_input = data.get("grupe", None)
    copii = data.get("copii", [])

    if not username or not email or not parola or not tip:
        return jsonify({"status": "error", "message": "Toate câmpurile de bază sunt obligatorii"}), 400

    tip_l = tip.lower()

    # Calculăm vârsta numerică (pentru compatibilitate DB) pe baza anului
    varsta_calc = None
    if data_nasterii:
        try:
            birth_year = int(data_nasterii.split("-")[0])  # YYYY-MM-DD
            current_year = datetime.now().year
            varsta_calc = current_year - birth_year
        except:
            varsta_calc = None

    # Validări specifice
    if tip_l == "sportiv":
        if not data_nasterii:
            return jsonify({"status": "error", "message": "Data nașterii este obligatorie pentru sportiv"}), 400
    elif tip_l == "antrenor":
        if not grupe_input:
            return jsonify({"status": "error", "message": "Grupele sunt obligatorii pentru antrenor"}), 400

    # Procesare copii (pt părinte)
    grupe = None
    copii_json = None
    if tip_l == "parinte":
        grupe_set = set()
        copii_curati = []
        for c in (copii or []):
            nume_c = (c.get("nume") or "").strip()
            grupa_c = (c.get("grupa") or "").strip()
            varsta_c = c.get("varsta")
            gen_c = _norm_gen(c.get("gen"))

            if not (nume_c or grupa_c or varsta_c or gen_c): continue

            if grupa_c: grupe_set.add(grupa_c)
            if isinstance(varsta_c, str) and varsta_c.isdigit(): varsta_c = int(varsta_c)

            copii_curati.append({
                "nume": nume_c, "grupa": grupa_c, "varsta": varsta_c, "gen": gen_c
            })

        if copii_curati:
            copii_json = json.dumps(copii_curati, ensure_ascii=False)
            grupe = ", ".join(sorted(g for g in grupe_set if g)) or None
    else:
        grupe = (grupe_input or None)

    hashed_parola = hash_password(parola)

    try:
        con = get_conn()
        cur = con.cursor()

        # Verificări unicitate (username/email) - Rămân la fel ca înainte
        cur.execute("SELECT 1 FROM cereri_utilizatori WHERE username = %s LIMIT 1", (username,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Username deja folosit (în cereri)"}), 409

        cur.execute("SELECT 1 FROM utilizatori WHERE username = %s LIMIT 1", (username,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Username deja folosit"}), 409

        cur.execute("SELECT 1 FROM cereri_utilizatori WHERE email = %s LIMIT 1", (email,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Email deja folosit (în cereri)"}), 409

        cur.execute("SELECT 1 FROM utilizatori WHERE email = %s LIMIT 1", (email,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Email deja folosit"}), 409

        # Inserare în cereri_utilizatori
        # Inserăm data_nasterii în coloana nouă, și varsta calculată în coloana veche
        cur.execute(
            """
            INSERT INTO cereri_utilizatori
                (username, email, parola, tip, varsta, data_nasterii, copii, grupe, nume_complet)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (username, email, hashed_parola, tip, varsta_calc, data_nasterii, copii_json, grupe, full_name),
        )
        con.commit()

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    try:
        trimite_email_confirmare(email, username)
    except Exception as e:
        print("[WARN] Email confirmare a eșuat:", e)

    return jsonify({"status": "success"}), 200
