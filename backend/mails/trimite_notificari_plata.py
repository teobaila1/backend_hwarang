import os
import resend
import psycopg2
import psycopg2.extras
from datetime import datetime
from flask import Blueprint, jsonify

# Definim Blueprint-ul pentru a putea fi apelat ca link
notificari_plata_bp = Blueprint('notificari_plata', __name__)

# Configurare Resend
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_NAME = "ACS Hwarang Sibiu <site@hwarang.ro>"

# URL Baza de date (se ia automat din Render Environment dacă e setat, sau fallback)
DB_URL = os.environ.get(
    "DATABASE_URL") or "postgresql://postgres.scjjlhlavtxqidbxwson:Hwarang2025@aws-1-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require"


def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def trimite_email_individual(destinatar, nume_parinte, luna_curenta):
    subiect = f"Reamintire Plată Cotizație - {luna_curenta}"

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
            <p>Cu respect,<br><strong>Echipa ACS Hwarang Academy Sibiu</strong></p>
            <hr>
            <small style="color: #777;">Mesaj automat trimis prin Hwarang Platform.</small>
        </div>
    </body>
    </html>
    """
    try:
        resend.Emails.send({
            "from": SENDER_NAME,
            "to": destinatar,
            "subject": subiect,
            "html": mesaj_html
        })
        return True
    except Exception as e:
        print(f"[EROARE MAIL] {destinatar}: {e}")
        return False


# --- RUTA SECRETĂ PE CARE O VA APELA CPANEL ---
@notificari_plata_bp.get("/api/cron/trigger_notificari_plata_secret_12345")
def trigger_notificari():
    # Verificare extra: Resend API Key
    if not resend.api_key:
        return jsonify({"status": "error", "message": "Lipseste RESEND_API_KEY"}), 500

    print(f"--- START JOB NOTIFICARE ({datetime.now()}) ---")

    luni_ro = {
        1: "Ianuarie", 2: "Februarie", 3: "Martie", 4: "Aprilie",
        5: "Mai", 6: "Iunie", 7: "Iulie", 8: "August",
        9: "Septembrie", 10: "Octombrie", 11: "Noiembrie", 12: "Decembrie"
    }
    luna_curenta = luni_ro[datetime.now().month]

    conn = None
    count_succes = 0
    count_total = 0

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Luăm părinții
        cur.execute("SELECT email, nume_complet FROM utilizatori WHERE rol = 'Parinte' AND email IS NOT NULL")
        parinti = cur.fetchall()
        count_total = len(parinti)

        for p in parinti:
            if p['email'] and '@' in p['email']:
                nume = p['nume_complet'] if p['nume_complet'] else "Părinte"
                if trimite_email_individual(p['email'], nume, luna_curenta):
                    count_succes += 1

        return jsonify({
            "status": "success",
            "message": f"Job rulat. Trimise: {count_succes}/{count_total}",
            "luna": luna_curenta
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if conn: conn.close()