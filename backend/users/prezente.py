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
                id_alocare BIGINT, -- Coloana nouă de legătură

                -- Legături (opțional le poți lăsa sau scoate pe cele vechi, dar cea nouă e importantă)
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

    # Ora României
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
        nume_grupa_text = "Fara Grupa"
        id_alocare_gasit = None  # Aici vom salva ID-ul din sportivi_pe_grupe

        if is_adult:
            # === 1. ADULT ===
            # Pas A: Luăm numele din utilizatori
            cur.execute("SELECT nume_complet, username FROM utilizatori WHERE id = %s", (qr_code,))
            row_user = cur.fetchone()
            if not row_user:
                return jsonify({"status": "error", "message": "Sportiv (Adult) negăsit."}), 404
            nume_sportiv = row_user['nume_complet'] or row_user['username']

            # Pas B: Căutăm ALOCAREA în sportivi_pe_grupe
            # Vrem să vedem dacă există în tabelul de legătură
            cur.execute("""
                SELECT id, id_grupa FROM sportivi_pe_grupe 
                WHERE id_sportiv_user = %s
            """, (qr_code,))
            row_alocare = cur.fetchone()

            if row_alocare:
                id_alocare_gasit = row_alocare['id']  # ID-ul unic al rândului (Legătura)

                # Opțional: Dacă ai un tabel 'grupe', poți lua numele de acolo folosind row_alocare['id_grupa']
                # Deocamdată luăm textul din utilizatori ca fallback sau setăm manual
                nume_grupa_text = "Seniori/Adulti (Alocat)"
            else:
                # Dacă nu e alocat, poți alege să dai eroare sau să îl lași să treacă
                # return jsonify({"status": "error", "message": "Sportivul nu este alocat niciunei grupe!"}), 400
                nume_grupa_text = "Ne-alocat"

            # Pas C: Inserăm
            cur.execute("""
                INSERT INTO prezente (id_sportiv_user, id_antrenor, nume_grupa, data_ora, id_alocare)
                VALUES (%s, %s, %s, %s, %s)
            """, (qr_code, antrenor_id, nume_grupa_text, acum_ro, id_alocare_gasit))

        else:
            # === 2. COPIL ===
            # Pas A: Luăm numele
            cur.execute("SELECT nume, grupa_text FROM copii WHERE id = %s", (qr_code,))
            row_copil = cur.fetchone()
            if not row_copil:
                return jsonify({"status": "error", "message": "Sportiv (Copil) negăsit."}), 404
            nume_sportiv = row_copil['nume']
            nume_grupa_text = row_copil['grupa_text']  # Păstrăm numele grupei text pentru afișare

            # Pas B: Căutăm ALOCAREA în sportivi_pe_grupe
            cur.execute("""
                SELECT id FROM sportivi_pe_grupe 
                WHERE id_sportiv_copil = %s
            """, (qr_code,))
            row_alocare = cur.fetchone()

            if row_alocare:
                id_alocare_gasit = row_alocare['id']
            else:
                # E posibil ca un copil să aibă 'grupa_text' completat, dar să nu fie încă în tabelul de legătură
                pass

                # Pas C: Inserăm
            cur.execute("""
                INSERT INTO prezente (id_sportiv_copil, id_antrenor, nume_grupa, data_ora, id_alocare)
                VALUES (%s, %s, %s, %s, %s)
            """, (qr_code, antrenor_id, nume_grupa_text, acum_ro, id_alocare_gasit))

        con.commit()

        ora_form = acum_ro.strftime("%H:%M")
        return jsonify({
            "status": "success",
            "message": f"Prezență: {nume_sportiv}",
            "detalii": f"Grupa: {nume_grupa_text} | Ora: {ora_form}"
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Eroare scan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()

# Ruta istoric rămâne neschimbată


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