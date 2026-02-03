import uuid
from datetime import datetime
import pytz
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from ..accounts.decorators import token_required

prezente_bp = Blueprint("prezente", __name__)


def _ensure_prezente_table():
    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS prezente (
                id SERIAL PRIMARY KEY,
                data_ora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                id_sportiv_copil TEXT,
                id_sportiv_user INT,
                id_antrenor INT,
                nume_grupa TEXT,
                id_alocare BIGINT, 
                CONSTRAINT fk_prezenta_alocare
                    FOREIGN KEY(id_alocare) 
                    REFERENCES sportivi_pe_grupe(id)
                    ON DELETE SET NULL
            )
        """)
        con.commit()
    except Exception as e:
        print(f"Eroare creare tabel prezente: {e}")
        con.rollback()
    finally:
        con.close()


_ensure_prezente_table()


@prezente_bp.post("/api/prezenta/scan")
@token_required
def scan_qr():
    data = request.get_json(silent=True) or {}
    qr_code = data.get("qr_code")
    antrenor_id = data.get("antrenor_id")

    if not qr_code:
        return jsonify({"status": "error", "message": "Cod invalid"}), 400

    try:
        tz_ro = pytz.timezone('Europe/Bucharest')
        acum_ro = datetime.now(tz_ro)
    except Exception as e:
        acum_ro = datetime.now()

    con = get_conn()
    try:
        cur = con.cursor()

        is_adult = str(qr_code).isdigit()
        nume_sportiv = ""
        nume_grupa_text = ""  # Vom completa cu numele real
        id_alocare_gasit = None

        if is_adult:
            # === 1. ADULT ===
            # FIX: Cerem și coloana 'grupe' ca să avem numele corect al grupei
            cur.execute("SELECT nume_complet, username, grupe FROM utilizatori WHERE id = %s", (qr_code,))
            row_user = cur.fetchone()
            if not row_user:
                return jsonify({"status": "error", "message": "Sportiv (Adult) negăsit."}), 404

            nume_sportiv = row_user['nume_complet'] or row_user['username']

            # FIX: Folosim numele grupei din tabelul utilizatori, nu textul hardcodat
            if row_user['grupe']:
                nume_grupa_text = row_user['grupe']
            else:
                nume_grupa_text = "Fara Grupa"

            # Căutăm ALOCAREA (pentru id_alocare)
            cur.execute("SELECT id FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (qr_code,))
            row_alocare = cur.fetchone()
            if row_alocare:
                id_alocare_gasit = row_alocare['id']

            cur.execute("""
                INSERT INTO prezente (id_sportiv_user, id_antrenor, nume_grupa, data_ora, id_alocare)
                VALUES (%s, %s, %s, %s, %s)
            """, (qr_code, antrenor_id, nume_grupa_text, acum_ro, id_alocare_gasit))

        else:
            # === 2. COPIL ===
            cur.execute("SELECT nume, grupa_text FROM copii WHERE id = %s", (qr_code,))
            row_copil = cur.fetchone()
            if not row_copil:
                return jsonify({"status": "error", "message": "Sportiv (Copil) negăsit."}), 404

            nume_sportiv = row_copil['nume']
            nume_grupa_text = row_copil['grupa_text']  # Aici era deja bine

            # Căutăm ALOCAREA
            cur.execute("SELECT id FROM sportivi_pe_grupe WHERE id_sportiv_copil = %s", (qr_code,))
            row_alocare = cur.fetchone()
            if row_alocare:
                id_alocare_gasit = row_alocare['id']

            cur.execute("""
                INSERT INTO prezente (id_sportiv_copil, id_antrenor, nume_grupa, data_ora, id_alocare)
                VALUES (%s, %s, %s, %s, %s)
            """, (qr_code, antrenor_id, nume_grupa_text, acum_ro, id_alocare_gasit))

        con.commit()

        ora_form = acum_ro.strftime("%H:%M")

        # FIX: Returnăm JSON-ul exact cum îl așteaptă frontend-ul (cu cheia 'nume')
        return jsonify({
            "status": "success",
            "message": f"Prezență: {nume_sportiv}",
            "nume": nume_sportiv,  # <--- Asta rezolvă 'undefined' pe telefon
            "grupa": nume_grupa_text,  # <--- Asta arată grupa corectă
            "ora": ora_form
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Eroare scan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


@prezente_bp.get("/api/prezenta/istoric/<sportiv_id>")
@token_required
def istoric_prezente(sportiv_id):
    con = get_conn()
    try:
        cur = con.cursor()
        is_adult = str(sportiv_id).isdigit()

        if is_adult:
            cur.execute("""
                SELECT data_ora FROM prezente 
                WHERE id_sportiv_user = %s 
                ORDER BY data_ora DESC LIMIT 50
            """, (sportiv_id,))
        else:
            cur.execute("""
                SELECT data_ora FROM prezente 
                WHERE id_sportiv_copil = %s 
                ORDER BY data_ora DESC LIMIT 50
            """, (sportiv_id,))

        rows = cur.fetchall()
        data = [str(r['data_ora']) for r in rows]

        return jsonify({"status": "success", "istoric": data}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()