import uuid
from datetime import datetime
import pytz
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

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


# --- SCANARE QR (Reparată: Fără argumente, ia userul din request) ---
@prezente_bp.post("/api/prezenta/scan")
@token_required
def scan_qr():
    # NU punem parametri la funcție (def scan_qr():), luăm din request
    data = request.get_json(silent=True) or {}
    qr_code = data.get("qr_code")

    # ID-ul antrenorului este pus pe request de decoratorul @token_required
    antrenor_id = getattr(request, 'user_id', None)

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

        # Logică: Cifre = Adult, Litere = Copil
        is_adult = str(qr_code).isdigit()

        nume_sportiv = ""
        nume_grupa_text = ""
        id_alocare_gasit = None

        if is_adult:
            # === ADULT ===
            cur.execute("SELECT nume_complet, username, grupe FROM utilizatori WHERE id = %s", (qr_code,))
            row_user = cur.fetchone()
            if not row_user:
                return jsonify({"status": "error", "message": "Sportiv (Adult) negăsit."}), 404

            nume_sportiv = row_user['nume_complet'] or row_user['username']
            nume_grupa_text = row_user['grupe'] or "Fara Grupa"

            cur.execute("SELECT id FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (qr_code,))
            row_alocare = cur.fetchone()
            if row_alocare:
                id_alocare_gasit = row_alocare['id']

            cur.execute("""
                INSERT INTO prezente (id_sportiv_user, id_antrenor, nume_grupa, data_ora, id_alocare)
                VALUES (%s, %s, %s, %s, %s)
            """, (qr_code, antrenor_id, nume_grupa_text, acum_ro, id_alocare_gasit))

        else:
            # === COPIL ===
            cur.execute("SELECT nume, grupa_text FROM copii WHERE id = %s", (qr_code,))
            row_copil = cur.fetchone()
            if not row_copil:
                return jsonify({"status": "error", "message": "Sportiv (Copil) negăsit."}), 404

            nume_sportiv = row_copil['nume']
            nume_grupa_text = row_copil['grupa_text']

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

        return jsonify({
            "status": "success",
            "message": f"Prezență: {nume_sportiv}",
            "nume": nume_sportiv,
            "grupa": nume_grupa_text,
            "ora": ora_form
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Eroare scan: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 2. ISTORIC PENTRU PĂRINTE (Actualizat) ---
@prezente_bp.get("/api/prezenta/istoric/<sportiv_id>")
@token_required
def istoric_prezente(sportiv_id):
    con = get_conn()
    try:
        cur = con.cursor()
        is_adult = str(sportiv_id).isdigit()

        # Luăm ultimele 30 de prezențe
        query = """
            SELECT data_ora, nume_grupa 
            FROM prezente 
            WHERE {col} = %s 
            ORDER BY data_ora DESC 
            LIMIT 30
        """
        col = "id_sportiv_user" if is_adult else "id_sportiv_copil"

        cur.execute(query.format(col=col), (sportiv_id,))
        rows = cur.fetchall()

        # Formatăm frumos pentru Frontend
        data_istoric = []
        for r in rows:
            dt = r['data_ora']
            # Exemplu: "12 Feb 2025 - 18:30"
            data_istoric.append({
                "raw": str(dt),
                "data": dt.strftime("%d.%m.%Y"),
                "ora": dt.strftime("%H:%M"),
                "grupa": r['nume_grupa'] or "-"
            })

        return jsonify({"status": "success", "istoric": data_istoric}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


@prezente_bp.get("/api/prezenta/grupa/<int:id_grupa>")
@token_required
def get_prezenta_grupa(id_grupa):
    """
    Returnează lista sportivilor și zilele exacte (1..31) în care au fost prezenți
    pentru luna și anul specificat.
    """
    # Citim luna și anul din URL (ex: ?luna=2&an=2026)
    # Dacă lipsesc, luăm luna curentă
    azi = datetime.now()
    try:
        luna = int(request.args.get('luna', azi.month))
        an = int(request.args.get('an', azi.year))
    except:
        luna = azi.month
        an = azi.year

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Luăm toți sportivii din grupă
        cur.execute("""
            SELECT 
                COALESCE(c.id, CAST(u.id AS TEXT)) as id_sportiv,
                COALESCE(c.nume, u.nume_complet) as nume,
                CASE WHEN c.id IS NOT NULL THEN 'copil' ELSE 'adult' END as tip
            FROM sportivi_pe_grupe sg
            LEFT JOIN copii c ON sg.id_sportiv_copil = c.id
            LEFT JOIN utilizatori u ON sg.id_sportiv_user = u.id
            WHERE sg.id_grupa = %s
            ORDER BY nume ASC
        """, (id_grupa,))
        sportivi = cur.fetchall()

        rezultate = []

        for s in sportivi:
            sid = s['id_sportiv']
            stip = s['tip']
            col_where = "id_sportiv_copil" if stip == 'copil' else "id_sportiv_user"

            # 2. Luăm ZILELE exacte din luna respectivă când a fost prezent
            # Returnează ex: [2, 5, 12, 14]
            cur.execute(f"""
                SELECT EXTRACT(DAY FROM data_ora) as zi
                FROM prezente 
                WHERE {col_where} = %s 
                  AND EXTRACT(MONTH FROM data_ora) = %s
                  AND EXTRACT(YEAR FROM data_ora) = %s
                ORDER BY data_ora ASC
            """, (sid, luna, an))

            rows_zile = cur.fetchall()
            zile_prezente = [int(r['zi']) for r in rows_zile]  # Lista de int-uri [5, 12, 20]

            rezultate.append({
                "id": sid,
                "nume": s['nume'],
                "tip": stip,
                "zile": zile_prezente,  # Trimitem lista de zile către React
                "total": len(zile_prezente)
            })

        return jsonify({
            "status": "success",
            "data": rezultate,
            "meta": {"luna": luna, "an": an}
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 4. CALENDAR PREZENȚE PENTRU UN SINGUR COPIL (PENTRU PĂRINȚI) ---
@prezente_bp.get("/api/prezenta/copil_calendar/<string:id_copil>")
@token_required
def get_prezenta_copil_calendar(id_copil):
    """
    Returnează datele calendaristice (zilele 1..31) pentru un singur copil.
    Formatul este identic cu cel de la grupă, dar lista conține un singur element.
    """
    azi = datetime.now()
    try:
        luna = int(request.args.get('luna', azi.month))
        an = int(request.args.get('an', azi.year))
    except:
        luna = azi.month
        an = azi.year

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Luăm datele copilului
        cur.execute("SELECT id, nume FROM copii WHERE id = %s", (id_copil,))
        copil = cur.fetchone()

        if not copil:
            return jsonify({"status": "error", "message": "Copil negăsit"}), 404

        # 2. Luăm ZILELE exacte din luna respectivă
        cur.execute("""
            SELECT EXTRACT(DAY FROM data_ora) as zi
            FROM prezente 
            WHERE id_sportiv_copil = %s 
              AND EXTRACT(MONTH FROM data_ora) = %s
              AND EXTRACT(YEAR FROM data_ora) = %s
            ORDER BY data_ora ASC
        """, (id_copil, luna, an))

        rows_zile = cur.fetchall()
        zile_prezente = [int(r['zi']) for r in rows_zile]

        # Returnăm o listă cu un singur obiect (pentru a fi compatibil cu TabelPrezenta)
        rezultat = [{
            "id": copil['id'],
            "nume": copil['nume'],
            "tip": "copil",
            "zile": zile_prezente,
            "total": len(zile_prezente)
        }]

        return jsonify({
            "status": "success",
            "data": rezultat,
            "meta": {"luna": luna, "an": an}
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()