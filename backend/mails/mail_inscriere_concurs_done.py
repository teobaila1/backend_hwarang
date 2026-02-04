import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# --- CONFIGURARE SMTP (Preluată din trimite_notificari_plata.py) ---
# Dacă aceste date sunt sensibile, ideal ar fi să le muți în .env
SMTP_HOST = "mail.hwarang.ro"
SMTP_PORT = 465  # SSL
SMTP_USER = "site@hwarang.ro"
# ATENȚIE: Asigură-te că parola este corectă (cea din trimite_notificari_plata.py)
SMTP_PASSWORD = "8bqZt5EhKbzHgQa"


def trimite_confirmare_inscriere(email_destinatar, nume_sportiv, nume_concurs, detalii_concurs=""):
    """
    Trimite un email de confirmare părintelui/sportivului după înscrierea la concurs.
    """
    if not email_destinatar or "@" not in email_destinatar:
        print(f"[MAIL-SKIP] Email invalid: {email_destinatar}")
        return False

    subiect = f"Confirmare Înscriere: {nume_concurs}"

    # Mesajul HTML
    mesaj_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
            <h2 style="color: #d32f2f; text-align: center;">Înscriere Confirmată!</h2>

            <p>Salut, <strong>{nume_sportiv}</strong>!</p>

            <p>Îți confirmăm cu succes înscrierea la concursul:</p>
            <h3 style="background-color: #f4f4f4; padding: 10px; border-left: 5px solid #d32f2f;">
                {nume_concurs}
            </h3>

            <p><strong>Detalii suplimentare:</strong><br>
            {detalii_concurs or "Mai multe detalii vor fi anunțate de antrenor."}
            </p>

            <br>
            <p>Mult succes la competiție!<br>
            <strong>Echipa ACS Hwarang Sibiu</strong></p>
            <hr>
            <small style="color: #777;">Acest email a fost generat automat.</small>
        </div>
    </body>
    </html>
    """

    try:
        # Construim email-ul
        msg = MIMEMultipart()
        msg['From'] = f"ACS Hwarang Sibiu <{SMTP_USER}>"
        msg['To'] = email_destinatar
        msg['Subject'] = subiect
        msg.attach(MIMEText(mesaj_html, 'html'))

        # Conectare și trimitere
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, email_destinatar, msg.as_string())
        server.quit()

        print(f"[MAIL-SUCCESS] Confirmare trimisă la {email_destinatar} pentru {nume_concurs}")
        return True

    except Exception as e:
        print(f"[MAIL-ERROR] Nu s-a putut trimite confirmarea la {email_destinatar}: {e}")
        return False