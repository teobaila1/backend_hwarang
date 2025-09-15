import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from textwrap import dedent
import json
import ast

# rulează ca modul:  python -m backend.mails.notificare_plati
from ..config import get_conn, DB_PATH


# ---------------- SMTP ----------------
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")  # ex: contul_tău@gmail.com
SMTP_PASS = os.getenv("SMTP_PASS")  # App Password (Gmail, cu 2FA)
# -------------------------------------


def safe_load_children(copii_json):
    """Parsează în siguranță coloana 'copii' din DB în listă de dict-uri."""
    if not copii_json:
        return []
    # 1) încercăm JSON standard
    try:
        return json.loads(copii_json)
    except Exception:
        pass
    # 2) uneori date vechi pot avea formatare tip Python -> încercăm literal_eval
    try:
        val = ast.literal_eval(copii_json)
        if isinstance(val, list):
            return val
    except Exception:
        pass
    return []


def send_email(to_addr: str, subject: str, body: str):
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


def main():
    # Trimite doar în ziua 20, exceptând dacă e setat FORCE_SEND=1 pentru test
    force = os.getenv("FORCE_SEND", "0").strip() == "1"
    today = datetime.now()
    if today.day != 20 and not force:
        print("Nu este 20 ale lunii (și FORCE_SEND nu este 1). Ieșire.")
        return

    print(f"[BOOT] DB: {DB_PATH}")
    con = get_conn()

    # părinți cu copii
    rows = con.execute(
        "SELECT username, email, copii FROM utilizatori WHERE LOWER(rol) = 'parinte'"
    ).fetchall()

    total = 0
    trimise = 0

    for r in rows:
        username = r["username"]
        email = r["email"]
        copii = safe_load_children(r["copii"])

        if not email:
            continue

        nume_copii = ", ".join(
            [str(c.get("nume", "")).strip() for c in copii if str(c.get("nume", "")).strip()]
        ) or "copilul / copiii dvs."

        body = dedent(f"""
            Bună, {username},

            Vă rugăm să achitați abonamentul lunar pentru: {nume_copii}.

            Termenul recomandat este sfârșitul lunii curente.

            Mulțumim!
            ACS Hwarang Academy
        """).strip()

        try:
            send_email(
                to_addr=email,
                subject="Notificare plată abonament - ACS Hwarang Academy",
                body=body
            )
            print(f"[OK] Email trimis către {email}")
            trimise += 1
        except Exception as e:
            print(f"[ERR] Trimitere către {email} a eșuat: {e}")

        total += 1

    print(f"[DONE] {trimise}/{total} emailuri trimise.")


if __name__ == "__main__":
    main()
