# import os
# import json
# import smtplib
# from email.mime.text import MIMEText
# from flask import Blueprint, request, jsonify
#
# from ..config import get_conn, DB_PATH
# from ..passwords.security import hash_password
#
# inregistrare_bp = Blueprint("inregistrare", __name__)
#
# # ---------- util: trimitere email (App Password / variabile de mediu) ----------
# SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
# SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
# SMTP_USER = os.getenv("SMTP_USER", "baila.teodor@gmail.com")  # ex: "contul_tau@gmail.com"
# SMTP_PASS = os.getenv("SMTP_PASS", "giqozfjtmxzscsri")  # ex: App Password (16 caractere)
#
# def _send_email(to_addr: str, subject: str, body: str):
#     if not (SMTP_USER and SMTP_PASS):
#         # Nu blocăm înregistrarea dacă nu e configurat emailul
#         print("[WARN] SMTP_USER/SMTP_PASS lipsesc. Sar peste trimiterea emailului.")
#         return
#     msg = MIMEText(body, _charset="utf-8")
#     msg["Subject"] = subject
#     msg["From"] = SMTP_USER
#     msg["To"] = to_addr
#     try:
#         with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
#             server.starttls()
#             server.login(SMTP_USER, SMTP_PASS)
#             server.send_message(msg)
#     except Exception as e:
#         print("[WARN] Eroare la trimiterea emailului:", e)
#
# def trimite_email_confirmare(destinatar: str, username: str):
#     body = (
#         f"Bună, {username}!\n\n"
#         "Cererea ta de creare cont la ACS Hwarang Academy a fost înregistrată cu succes. "
#         "Te vom contacta după aprobare."
#     )
#     _send_email(destinatar, "Confirmare creare cont - ACS Hwarang Academy Sibiu", body)
#
# def trimite_email_acceptare(destinatar: str, username: str):
#     body = (
#         f"Bună, {username}!\n\n"
#         "Cererea ta de creare cont a fost ACCEPTATĂ. Te poți autentifica pe site-ul ACS Hwarang Academy."
#     )
#     _send_email(destinatar, "Cerere acceptată - ACS Hwarang Academy", body)
#
# def trimite_email_respingere(destinatar: str, username: str):
#     body = (
#         f"Bună, {username}!\n\n"
#         "Cererea ta de creare cont a fost RESPINSĂ. Dacă ai întrebări, te rugăm să ne contactezi."
#     )
#     _send_email(destinatar, "Cerere respinsă - ACS Hwarang Academy", body)
# # ------------------------------------------------------------------------------
#
# def _norm_gen(v):
#     """Normalizează diverse forme în 'M' / 'F' sau None."""
#     if v is None:
#         return None
#     s = str(v).strip().lower()
#     if s in {"m", "masculin", "male", "b", "boy"}:
#         return "M"
#     if s in {"f", "feminin", "female", "g", "girl"}:
#         return "F"
#     return None
#
# @inregistrare_bp.post("/api/register")
# def register():
#     data = request.get_json(silent=True) or {}
#
#     username = (data.get("username") or "").strip()
#     full_name = (data.get("nume_complet") or "").strip()
#     email = (data.get("email") or "").strip()
#     parola = data.get("password") or data.get("parola")
#     tip = (data.get("tip") or "").strip()            # "Parinte", "Sportiv", "Antrenor", "AntrenorExtern"
#     varsta = data.get("varsta")
#     grupe_input = data.get("grupe", None)            # pentru Antrenor / AntrenorExtern
#     copii = data.get("copii", [])                    # listă de copii pentru Părinte (opțional!)
#
#     # Validări minime
#     if not username or not email or not parola or not tip:
#         return jsonify({"status": "error", "message": "Toate câmpurile de bază sunt obligatorii"}), 400
#
#     tip_l = tip.lower()
#     if tip_l in ("parinte", "sportiv"):
#         if varsta is None and tip_l == "sportiv":
#             return jsonify({"status": "error", "message": "Vârsta este obligatorie pentru sportiv"}), 400
#     elif tip_l == "antrenor":
#         if not grupe_input:
#             return jsonify({"status": "error", "message": "Grupele sunt obligatorii pentru antrenor"}), 400
#     elif tip_l == "antrenorextern":
#         pass
#     else:
#         return jsonify({"status": "error", "message": "Tip de utilizator necunoscut"}), 400
#
#     # Derivă grupe pentru părinte din copii (dacă există); copii sunt OPCIONALI
#     grupe = None
#     copii_json = None
#     if tip_l == "parinte":
#         grupe_set = set()
#         copii_curati = []
#         for c in (copii or []):
#             # acceptă doar intrări cu măcar un câmp completat
#             nume_c   = (c.get("nume")  or "").strip()
#             grupa_c  = (c.get("grupa") or "").strip()
#             varsta_c = c.get("varsta")
#             gen_c    = _norm_gen(c.get("gen"))
#
#             if not (nume_c or grupa_c or varsta_c or gen_c):
#                 continue  # rând gol -> ignor
#
#             if grupa_c:
#                 grupe_set.add(grupa_c)
#
#             if isinstance(varsta_c, str) and varsta_c.isdigit():
#                 varsta_c = int(varsta_c)
#
#             copii_curati.append({
#                 "nume":   nume_c,
#                 "grupa":  grupa_c,
#                 "varsta": varsta_c,
#                 "gen":    gen_c
#             })
#
#         if copii_curati:
#             copii_json = json.dumps(copii_curati, ensure_ascii=False)
#             grupe = ", ".join(sorted(g for g in grupe_set if g)) or None
#         else:
#             copii_json = None
#             grupe = None
#     else:
#         copii_json = None
#         grupe = (grupe_input or None)
#
#     hashed_parola = hash_password(parola)
#
#     try:
#         con = get_conn()
#         cur = con.cursor()
#
#         # Unicitate username/email atât în cereri_utilizatori cât și în utilizatori
#         cur.execute("SELECT 1 FROM cereri_utilizatori WHERE username = ? LIMIT 1", (username,))
#         if cur.fetchone():
#             return jsonify({"status": "error", "message": "Username deja folosit (în cereri)"}), 409
#
#         cur.execute("SELECT 1 FROM utilizatori WHERE username = ? LIMIT 1", (username,))
#         if cur.fetchone():
#             return jsonify({"status": "error", "message": "Username deja folosit"}), 409
#
#         cur.execute("SELECT 1 FROM cereri_utilizatori WHERE email = ? LIMIT 1", (email,))
#         if cur.fetchone():
#             return jsonify({"status": "error", "message": "Email deja folosit (în cereri)"}), 409
#
#         cur.execute("SELECT 1 FROM utilizatori WHERE email = ? LIMIT 1", (email,))
#         if cur.fetchone():
#             return jsonify({"status": "error", "message": "Email deja folosit"}), 409
#
#         # Inserare cerere (copii/grupe pot fi NULL)
#         cur.execute("""
#             INSERT INTO cereri_utilizatori (username, email, parola, tip, varsta, copii, grupe, nume_complet)
#             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
#         """, (username, email, hashed_parola, tip, varsta, copii_json, grupe, full_name))
#         con.commit()
#
#     except Exception as e:
#         return jsonify({"status": "error", "message": str(e)}), 500
#
#     # Trimitere email după commit (non-blocking)
#     try:
#         trimite_email_confirmare(email, username)
#     except Exception as e:
#         print("[WARN] Email confirmare a eșuat:", e)
#
#     return jsonify({"status": "success"}), 200




import os
import json
import ssl
import smtplib
from email.mime.text import MIMEText
from urllib import request as urlrequest

from flask import Blueprint, request, jsonify

from ..config import get_conn, DB_PATH
from ..passwords.security import hash_password

inregistrare_bp = Blueprint("inregistrare", __name__)

# ========== Email config ==========
# 1) Provider HTTP (Resend) – recomandat pe Render
RESEND_API_KEY = os.getenv("RESEND_API_KEY")  # pune cheia în Render > Environment
FROM_EMAIL = os.getenv("FROM_EMAIL", os.getenv("SMTP_USER", "no-reply@acshwarang.onresend.com"))

# 2) SMTP fallback (merge local)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SSL direct (nu STARTTLS)
SMTP_USER = os.getenv("SMTP_USER")              # ex: "contul_tău@gmail.com"
SMTP_PASS = os.getenv("SMTP_PASS")              # App Password (16 caractere pt. Gmail)
# ==================================


def _send_email_http_first(to_addr: str, subject: str, body_text: str):
    """
    Trimite mail în ordinea: Resend (HTTP) -> SMTP SSL(465) -> fallback log.
    NU aruncă excepții mai departe (nu vrem 500 la client dacă eșuează e-mailul).
    """
    body_html = f"<p>{body_text.replace(chr(10), '<br/>')}</p>"

    # --- 1) Resend API (HTTP) ---
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
                print(f"[MAIL] Resend către {to_addr}: {resp.status}")
                return
        except Exception as e:
            print("[WARN] Resend a eșuat, încerc SMTP:", e)

    # --- 2) SMTP SSL(465) ---
    if SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEText(body_text, _charset="utf-8")
            msg["Subject"] = subject
            msg["From"] = FROM_EMAIL or SMTP_USER
            msg["To"] = to_addr

            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(msg["From"], [to_addr], msg.as_string())
                print(f"[MAIL] SMTP către {to_addr}")
                return
        except Exception as e:
            print("[WARN] SMTP a eșuat:", e)

    # --- 3) fallback log (nu blocăm fluxul) ---
    print(f"[MAIL-FAKE] către {to_addr}: {subject} | {body_text}")


def trimite_email_confirmare(destinatar: str, username: str):
    body = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont la ACS Hwarang Academy a fost înregistrată cu succes. "
        "Te vom contacta după aprobare."
    )
    _send_email_http_first(destinatar, "Confirmare creare cont - ACS Hwarang Academy Sibiu", body)


def trimite_email_acceptare(destinatar: str, username: str):
    body = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont a fost ACCEPTATĂ. Te poți autentifica pe site-ul ACS Hwarang Academy."
    )
    _send_email_http_first(destinatar, "Cerere acceptată - ACS Hwarang Academy", body)


def trimite_email_respingere(destinatar: str, username: str):
    body = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont a fost RESPINSĂ. Dacă ai întrebări, te rugăm să ne contactezi."
    )
    _send_email_http_first(destinatar, "Cerere respinsă - ACS Hwarang Academy", body)


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
        cur.execute("SELECT 1 FROM cereri_utilizatori WHERE username = ? LIMIT 1", (username,))
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Username deja folosit (în cereri)"}), 409

        cur.execute("SELECT 1 FROM utilizatori WHERE username = ? LIMIT 1", (username,))
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Username deja folosit"}), 409

        cur.execute("SELECT 1 FROM cereri_utilizatori WHERE email = ? LIMIT 1", (email,))
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Email deja folosit (în cereri)"}), 409

        cur.execute("SELECT 1 FROM utilizatori WHERE email = ? LIMIT 1", (email,))
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Email deja folosit"}), 409

        # Inserare cerere (copii/grupe pot fi NULL)
        cur.execute("""
            INSERT INTO cereri_utilizatori (username, email, parola, tip, varsta, copii, grupe, nume_complet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, email, hashed_parola, tip, varsta, copii_json, grupe, full_name))
        con.commit()

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

    # Trimitere email după commit (non-blocking)
    try:
        trimite_email_confirmare(email, username)
    except Exception as e:
        print("[WARN] Email confirmare a eșuat:", e)

    return jsonify({"status": "success"}), 200
