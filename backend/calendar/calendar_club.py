from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

calendar_club_bp = Blueprint('calendar_club', __name__)


def _ensure_calendar_table():
    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS calendar_club (
                id SERIAL PRIMARY KEY,
                titlu TEXT NOT NULL,
                data_start TIMESTAMP NOT NULL,
                data_sfarsit TIMESTAMP,
                locatie TEXT,
                descriere TEXT,
                tip_eveniment TEXT DEFAULT 'Competitie' 
            )
        """)
        con.commit()
    except Exception as e:
        print(f"Eroare tabel calendar: {e}")
        con.rollback()
    finally:
        con.close()


_ensure_calendar_table()


# --- 1. LISTARE (Public) ---
@calendar_club_bp.get("/api/calendar/evenimente")
def get_events():
    con = get_conn()
    try:
        cur = con.cursor()

        # MODIFICARE AICI: DESC (Descrescător)
        # Evenimentele cu data cea mai mare (viitor) vor fi primele
        cur.execute("SELECT * FROM calendar_club ORDER BY data_start DESC")

        rows = cur.fetchall()

        events = []
        for r in rows:
            events.append({
                "id": r['id'],
                "titlu": r['titlu'],
                "start": str(r['data_start']),
                "end": str(r['data_sfarsit']) if r['data_sfarsit'] else None,
                "locatie": r['locatie'],
                "descriere": r['descriere'],
                "tip": r['tip_eveniment']
            })
        return jsonify(events), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 2. ADĂUGARE (Doar Admin) ---
@calendar_club_bp.post("/api/calendar/evenimente")
@token_required
def add_event():
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403

    data = request.get_json() or {}
    titlu = data.get("titlu")
    start = data.get("start")

    if not titlu or not start:
        return jsonify({"status": "error", "message": "Titlu și Data Start sunt obligatorii"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO calendar_club (titlu, data_start, data_sfarsit, locatie, descriere, tip_eveniment)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (titlu, start, data.get("end"), data.get("locatie"), data.get("descriere"), data.get("tip")))
        con.commit()
        return jsonify({"status": "success", "message": "Eveniment adăugat!"}), 201
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 3. ȘTERGERE (Doar Admin) ---
@calendar_club_bp.delete("/api/calendar/evenimente/<int:event_id>")
@token_required
def delete_event(event_id):
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403

    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM calendar_club WHERE id = %s", (event_id,))
        con.commit()
        return jsonify({"status": "success", "message": "Eveniment șters"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 4. EDITARE (Doar Admin) ---
@calendar_club_bp.put("/api/calendar/evenimente/<int:event_id>")
@token_required
def edit_event(event_id):
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403

    data = request.get_json() or {}
    titlu = data.get("titlu")
    start = data.get("start")

    if not titlu or not start:
        return jsonify({"status": "error", "message": "Titlu și Data Start sunt obligatorii"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        # Verificăm dacă există
        cur.execute("SELECT id FROM calendar_club WHERE id = %s", (event_id,))
        if not cur.fetchone():
            return jsonify({"status": "error", "message": "Evenimentul nu există"}), 404

        cur.execute("""
            UPDATE calendar_club 
            SET titlu = %s, data_start = %s, data_sfarsit = %s, 
                locatie = %s, descriere = %s, tip_eveniment = %s
            WHERE id = %s
        """, (titlu, start, data.get("end"), data.get("locatie"), data.get("descriere"), data.get("tip"), event_id))
        con.commit()
        return jsonify({"status": "success", "message": "Eveniment actualizat!"}), 200
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()