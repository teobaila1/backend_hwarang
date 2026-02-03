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
                nume_grupa TEXT 
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

    # --- CALCULĂM ORA ROMÂNIEI ---
    try:
        tz_ro = pytz.timezone('Europe/Bucharest')
        acum_ro = datetime.now(tz_ro)
    except Exception as e:
        print(f"Eroare timezone: {e}")
        acum_ro = datetime.now()  # Fallback
    # -----------------------------

    con = get_conn()
    try:
        cur = con.cursor()

        is_adult = str(qr_code).isdigit()
        nume_sportiv = ""
        grupa_sportiv = None

        if is_adult:
            # === CAZUL 1: ADULT (UTILIZATOR) ===
            cur.execute("SELECT nume_complet, username, grupa FROM utilizatori WHERE id = %s", (qr_code,))
            row = cur.fetchone()

            if not row:
                return jsonify({"status": "error", "message": "Sportiv (Adult) negăsit."}), 404

            nume_sportiv = row['nume_complet'] or row['username']

            # Luăm grupa reală din baza de date
            if row['grupa'] and str(row['grupa']).strip():
                grupa_sportiv = row['grupa']
            else:
                grupa_sportiv = "Seniori/Adulti"

            # Inserăm prezența
            cur.execute("""
                INSERT INTO prezente (id_sportiv_user, id_antrenor, nume_grupa, data_ora)
                VALUES (%s, %s, %s, %s)
            """, (qr_code, antrenor_id, grupa_sportiv, acum_ro))

        else:
            # === CAZUL 2: COPIL (Această parte lipsea la tine) ===
            cur.execute("SELECT nume, grupa FROM copii WHERE id = %s", (qr_code,))
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Sportiv (Copil) negăsit."}), 404

            nume_sportiv = row['nume']
            grupa_sportiv = row['grupa']

            # Inserăm prezența
            cur.execute("""
                INSERT INTO prezente (id_sportiv_copil, id_antrenor, nume_grupa, data_ora)
                VALUES (%s, %s, %s, %s)
            """, (qr_code, antrenor_id, grupa_sportiv, acum_ro))

        con.commit()

        # Formatăm ora pentru răspunsul vizual (ex: 18:30)
        ora_form = acum_ro.strftime("%H:%M")

        return jsonify({
            "status": "success",
            "message": f"Prezență: {nume_sportiv} ({ora_form})",
            "nume": nume_sportiv,
            "grupa": grupa_sportiv
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Eroare scan: {e}")
        return jsonify({"status": "error", "message": "Eroare server"}), 500
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