import os
import resend

# Preluăm cheia din Environment Variables (de pe Render)
resend.api_key = os.environ.get("RESEND_API_KEY")


def trimite_confirmare_inscriere(email_destinatar, nume_sportiv, nume_concurs, detalii_concurs=""):
    """
    Trimite un email de confirmare prin API-ul Resend (nu este blocat de Render).
    """
    if not email_destinatar or "@" not in email_destinatar:
        print(f"[MAIL-SKIP] Email invalid: {email_destinatar}")
        return False

    subiect = f"Confirmare Înscriere: {nume_concurs}"

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
            <small style="color: #777;">Acest email a fost generat automat prin platforma Hwarang.</small>
        </div>
    </body>
    </html>
    """

    try:
        # TRIMITERE PRIN RESEND API
        r = resend.Emails.send({
            "from": "ACS Hwarang Sibiu <site@hwarang.ro>",
            "to": email_destinatar,
            "subject": subiect,
            "html": mesaj_html
        })

        print(f"[MAIL-SUCCESS] Email trimis catre {email_destinatar} (ID: {r.get('id')})")
        return True

    except Exception as e:
        print(f"[MAIL-ERROR] Resend API Error: {e}")
        return False