import json
import os
from threading import Thread
from urllib import request as urlrequest


RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
FROM_EMAIL = os.getenv("FROM_EMAIL", "ACS Hwarang Sibiu <site@hwarang.ro>").strip()


def send_email_http(to_addr: str, subject: str, html: str, text: str = "") -> bool:
    if not RESEND_API_KEY:
        raise RuntimeError("Lipsește RESEND_API_KEY")

    payload = json.dumps({
        "from": FROM_EMAIL,
        "to": [to_addr],
        "subject": subject,
        "html": html,
        "text": text or ""
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
    with urlrequest.urlopen(req, timeout=12) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Resend a răspuns cu statusul {response.status}")
        print(f"[MAIL] Resend status={response.status} to={to_addr}")
    return True


def send_email_in_background(to_addr: str, subject: str, html: str, text: str = ""):
    def deliver():
        try:
            send_email_http(to_addr, subject, html, text)
        except Exception as exc:
            print(f"[MAIL ERROR] Trimitere către {to_addr} eșuată: {exc}")

    Thread(target=deliver, daemon=True).start()


def send_emails_in_background(messages):
    def deliver_batch():
        for message in messages:
            try:
                send_email_http(
                    message["to"],
                    message["subject"],
                    message["html"],
                    message.get("text", "")
                )
            except Exception as exc:
                print(f"[MAIL ERROR] Trimitere către {message['to']} eșuată: {exc}")

    Thread(target=deliver_batch, daemon=True).start()
