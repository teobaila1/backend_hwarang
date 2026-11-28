from html import escape
from urllib.parse import urlparse
from flask import Blueprint, request, jsonify

from ..accounts.decorators import token_required, admin_required
from ..config import get_conn  # o singură sursă pentru DB
from ..mails.emailer import send_emails_in_background

adauga_concurs_bp = Blueprint('adauga_concurs', __name__)

@adauga_concurs_bp.post('/api/adauga_concurs')
@token_required
@admin_required
def adauga_concurs():
    data = request.get_json(silent=True) or {}
    nume = (data.get('nume') or '').strip()
    perioada = (data.get('perioada') or '').strip()
    locatie = (data.get('locatie') or '').strip()
    # --- MODIFICARE AICI: Citim bifa ---
    cere_inaltime = data.get('cere_inaltime', False)
    # -----------------------------------

    if not nume or not perioada or not locatie:
        return jsonify({"status": "error", "message": "Câmpuri obligatorii: nume, perioada, locatie"}), 400

    try:
        con = get_conn()

        # (opțional) prevenim duplicatele pe (nume, perioada, locatie)
        dup = con.execute(
            """SELECT 1 FROM concursuri
               WHERE LOWER(nume)=LOWER(%s) AND perioada=%s AND LOWER(locatie)=LOWER(%s)
               LIMIT 1""",
            (nume, perioada, locatie)
        ).fetchone()
        if dup:
            return jsonify({"status": "error", "message": "Concurs deja existent"}), 409

        con.execute(
            "INSERT INTO concursuri (nume, perioada, locatie, cere_inaltime) VALUES (%s, %s, %s, %s)",
            (nume, perioada, locatie, cere_inaltime)
        )
        con.commit()

        return jsonify({"status": "success", "message": "Concurs adăugat"}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@adauga_concurs_bp.post('/api/concursuri/anunta')
@token_required
@admin_required
def anunta_concurs():
    data = request.get_json(silent=True) or {}
    nume = (data.get('nume') or '').strip()
    perioada = (data.get('perioada') or '').strip()
    locatie = (data.get('locatie') or '').strip()
    link_inscriere = (data.get('link_inscriere') or '').strip()
    parsed_link = urlparse(link_inscriere)

    if not nume or not perioada or not locatie or not link_inscriere:
        return jsonify({
            "status": "error",
            "message": "Numele, perioada, locația și linkul de înscriere sunt obligatorii."
        }), 400
    if parsed_link.scheme not in {'http', 'https'} or not parsed_link.netloc:
        return jsonify({"status": "error", "message": "Linkul de înscriere nu este valid."}), 400

    conn = get_conn()
    try:
        recipients = conn.execute("""
            SELECT DISTINCT LOWER(email) AS email
            FROM utilizatori
            WHERE rol IN ('Parinte', 'Sportiv')
              AND email IS NOT NULL
              AND TRIM(email) != ''
              AND LOWER(email) NOT LIKE 'placeholder_%'
        """).fetchall()
        emails = [row['email'] for row in recipients]

        if len(emails) > 100:
            return jsonify({
                "status": "error",
                "message": "Anunțul depășește limita de 100 de destinatari pentru o singură trimitere."
            }), 422

        safe_name = escape(nume)
        safe_period = escape(perioada)
        safe_location = escape(locatie)
        safe_link = escape(link_inscriere, quote=True)
        messages = [{
            "to": email,
            "subject": f"Înscrieri deschise: {nume} - ACS Hwarang",
            "html": (
                f"<p>Înscrierile sunt deschise pentru <strong>{safe_name}</strong>.</p>"
                f"<p>Data/perioada: {safe_period}<br>Locația: {safe_location}</p>"
                f'<p><a href="{safe_link}">Vezi detaliile și înscrie-te</a></p>'
            ),
            "text": (
                f"Înscrierile sunt deschise pentru {nume}. Data/perioada: {perioada}. "
                f"Locația: {locatie}. Link de înscriere: {link_inscriere}"
            )
        } for email in emails]

        confirmare_necesara = f"CONFIRM {len(messages)} EMAILURI"
        if messages and data.get('confirmare') != confirmare_necesara:
            return jsonify({
                "status": "preview",
                "notificari_estimate": len(messages),
                "notificari_programate": 0,
                "confirmare_necesara": confirmare_necesara,
                "message": "Previzualizare: nu s-a trimis niciun email."
            }), 200

        if messages:
            send_emails_in_background(messages)

        return jsonify({
            "status": "success",
            "notificari_programate": len(messages)
        }), 200
    except Exception as e:
        print(f"[EROARE ANUNȚ CONCURS]: {e}")
        return jsonify({"status": "error", "message": "Eroare la pregătirea anunțului."}), 500
    finally:
        conn.close()
