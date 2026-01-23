# backend/cron/trimite_notificari_plata.py

import sys
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import psycopg2
import psycopg2.extras
from datetime import datetime

# --- CONFIGURARE ---
# Pune aici datele tale reale de DB si Email
DB_URL = "postgresql://user:pass@host:port/dbname"
SMTP_EMAIL = "contact@hwarang.ro"
SMTP_PASSWORD = "parola_ta_de_app_sau_mail"
SMTP_HOST = "mail.hwarang.ro"  # sau smtp.gmail.com
SMTP_PORT = 465  # SSL


def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def trimite_email(destinatar, nume_parinte):
    subiect = "Reamintire Plată Cotizație Club Hwarang"

    luna_curenta = datetime.now().strftime("%B")  # ex: January

    # Textul Emailului (HTML)
    mesaj_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <h2 style="color: #d32f2f;">Salutare, {nume_parinte}!</h2>
        <p>Sperăm că ai o lună excelentă.</p>
        <p>Acesta este un mesaj automat de reamintire pentru achitarea <strong>cotizației lunare</strong> aferente lunii curente.</p>
        <p>Te rugăm să ignori acest mesaj dacă ai efectuat deja plata.</p>
        <br>
        <p>Cu respect,<br>
        <strong>Echipa ACS Hwarang Academy Sibiu</strong></p>
    </body>
    </html>
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_EMAIL
        msg['To'] = destinatar
        msg['Subject'] = subiect
        msg.attach(MIMEText(mesaj_html, 'html'))

        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, destinatar, msg.as_string())
        server.quit()
        print(f"[OK] Email trimis catre {destinatar}")
    except Exception as e:
        print(f"[EROARE] Nu s-a putut trimite la {destinatar}: {e}")


def job_notificare():
    print("--- START JOB NOTIFICARE PLATA ---")
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # Selectam toti parintii activi
        cur.execute("SELECT email, nume_complet FROM utilizatori WHERE rol = 'Parinte'")
        parinti = cur.fetchall()

        for p in parinti:
            if p['email']:
                trimite_email(p['email'], p['nume_complet'] or "Părinte")

    except Exception as e:
        print(f"Eroare generala DB: {e}")
    finally:
        conn.close()
    print("--- STOP JOB ---")


if __name__ == "__main__":
    job_notificare()