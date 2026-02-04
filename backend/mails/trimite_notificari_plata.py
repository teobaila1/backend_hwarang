import os
import resend
import psycopg2
import psycopg2.extras
from datetime import datetime
import sys

# ================= CONFIGURARE =================

# 1. Datele Bazei de Date (Supabase) - Rămân neschimbate
DB_URL = "postgresql://postgres.scjjlhlavtxqidbxwson:Hwarang2025@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require"

# 2. Configurare Resend
resend.api_key = os.environ.get("RESEND_API_KEY")

# Adresa de expediere (trebuie să fie domeniul verificat)
SENDER_NAME = "ACS Hwarang Sibiu <site@hwarang.ro>"


# ==================================================================

def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def trimite_email(destinatar, nume_parinte):
    # Mapare luni in Romana
    luni_ro = {
        1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie",
        5: "Mai", 6: "Iunie", 7: "Iulie", 8: "August",
        9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
    }
    luna_curenta = luni_ro[datetime.now().month]

    subiect = f"Reamintire Plată Cotizație - {luna_curenta}"

    # Mesajul HTML (Ce vede părintele)
    mesaj_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
            <h2 style="color: #d32f2f; text-align: center;">Salutare, {nume_parinte}!</h2>

            <p>Sperăm că ai o lună excelentă.</p>

            <p>Acesta este un mesaj automat de reamintire pentru achitarea <strong>cotizației lunare</strong> aferente lunii <strong>{luna_curenta}</strong>.</p>

            <p style="background-color: #f9f9f9; padding: 15px; border-left: 5px solid #d32f2f;">
                Te rugăm să ignori acest mesaj dacă ai efectuat deja plata în ultimele zile.
            </p>

            <br>
            <p>Cu respect,<br>
            <strong>Echipa ACS Hwarang Academy Sibiu</strong></p>
            <hr>
            <small style="color: #777;">Acest email a fost generat automat prin platforma Hwarang.</small>
        </div>
    </body>
    </html>
    """

    try:
        # TRIMITERE PRIN RESEND API
        r = resend.Emails.send({
            "from": SENDER_NAME,
            "to": destinatar,
            "subject": subiect,
            "html": mesaj_html
        })

        print(f"[SUCCES] Email trimis catre: {destinatar} (ID: {r.get('id')})")

    except Exception as e:
        print(f"[EROARE] Nu s-a putut trimite la {destinatar}. Motiv: {e}")


def job_notificare():
    print(f"--- START JOB NOTIFICARE ({datetime.now()}) ---")

    if not resend.api_key:
        print("[CRITIC] Nu am găsit RESEND_API_KEY în variabilele de mediu!")
        return

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Selectam doar părinții care au email valid
        cur.execute("SELECT email, nume_complet FROM utilizatori WHERE rol = 'Parinte' AND email IS NOT NULL")
        parinti = cur.fetchall()

        print(f"Am gasit {len(parinti)} parinti in baza de date.")

        for p in parinti:
            if p['email'] and '@' in p['email']:
                nume = p['nume_complet'] if p['nume_complet'] else "Părinte"
                trimite_email(p['email'], nume)
            else:
                print(f"[SKIP] Email invalid pentru: {p.get('nume_complet')}")

    except Exception as e:
        print(f"[CRITIC] Eroare generala Baza de Date: {e}")
    finally:
        if conn:
            conn.close()

    print("--- STOP JOB ---")


if __name__ == "__main__":
    job_notificare()