import os
import json
from urllib import request as urlrequest

# Cheia Resend (Settings → API Keys)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()

# Adresa „from”
# Pentru start rapid poți lăsa domeniul implicit Resend:
#   no-reply@acshwarang.onresend.com
# (nu necesită DNS). Când îți verifici propriul domeniu, pune adresa ta.
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@acshwarang.onresend.com").strip()


def send_email_http(to_addr: str, subject: str, html: str, text: str = "") -> bool:
    """
    Trimite email via Resend API (HTTP).
    Returnează True dacă statusul HTTP e 2xx. Nu ridică excepții mai departe.
    """
    if not RESEND_API_KEY:
        print(f"[MAIL-FAKE] (lipsă RESEND_API_KEY) către {to_addr}: {subject}")
        return False

    payload = json.dumps({
        "from": FROM_EMAIL,
        "to": [to_addr],
        "subject": subject,
        "html": html,
        "text": text or ""
    }).encode("utf-8")

    try:
        req = urlrequest.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=12) as resp:
            ok = 200 <= resp.status < 300
            print(f"[MAIL] Resend status={resp.status} ok={ok} to={to_addr}")
            return ok
    except Exception as e:
        print("[MAIL] Resend error:", e)
        return False
