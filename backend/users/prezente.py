import uuid
from datetime import datetime
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
                id_grupa INT
            )
        """)
        con.commit()
    except Exception as e:
        print(f"Eroare creare tabel prezente: {e}")
        con.rollback()
    finally:
        con.close()


# Apelăm funcția la pornire (sau la primul request)
_ensure_prezente_table()


@prezente_bp.post("/api/prezenta/scan")
@token_required
def scan_qr():
    """
    Antrenorul scanează un cod QR.
    Payload așteptat: { "qr_content": "ID_SPORTIV" }
    """
    data = request.get_json(silent=True) or {}
    qr_code = data.get("qr_code")  # Acesta este ID-ul sportivului
    antrenor_id = data.get("antrenor_id")  # Sau il luam din token daca vrei, dar frontendul il poate trimite

    if not qr_code:
        return jsonify({"status": "error", "message": "Cod invalid"}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Identificăm tipul sportivului (Copil vs Adult)
        # Logica noastră: Adulții au ID numeric (ex: 25), Copiii au UUID (lung)
        is_adult = str(qr_code).isdigit()

        nume_sportiv = ""

        if is_adult:
            # Verificăm dacă există adultul
            cur.execute("SELECT nume_complet, username FROM utilizatori WHERE id = %s", (qr_code,))
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Sportiv (Adult) negăsit."}), 404
            nume_sportiv = row['nume_complet'] or row['username']

            # Inserăm prezența
            cur.execute("""
                INSERT INTO prezente (id_sportiv_user, id_antrenor)
                VALUES (%s, %s)
            """, (qr_code, antrenor_id))

        else:
            # Verificăm dacă există copilul
            cur.execute("SELECT nume FROM copii WHERE id = %s", (qr_code,))
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Sportiv (Copil) negăsit."}), 404
            nume_sportiv = row['nume']

            # Inserăm prezența
            cur.execute("""
                INSERT INTO prezente (id_sportiv_copil, id_antrenor)
                VALUES (%s, %s)
            """, (qr_code, antrenor_id))

        con.commit()

        # Returnăm numele ca antrenorul să vadă pe ecran "Prezență confirmată: Ion Popescu"
        return jsonify({
            "status": "success",
            "message": f"Prezență înregistrată: {nume_sportiv}",
            "nume": nume_sportiv
        }), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


@prezente_bp.get("/api/prezenta/istoric/<sportiv_id>")
@token_required
def istoric_prezente(sportiv_id):
    # Această rută va fi folosită în profilul sportivului să vadă când a fost prezent
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