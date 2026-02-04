from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required, admin_required
import datetime

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
                tip_eveniment TEXT DEFAULT 'General'
            )
        """)
        con.commit()
    except Exception as e:
        print(f"Eroare tabel calendar: {e}")
        con.rollback()
    finally:
        con.close()


_ensure_calendar_table()


# --- 1. LISTARE EVENIMENTE (Public sau User Logat) ---
@calendar_club_bp.get("/api/calendar/evenimente")
def get_events():
    con = get_conn()
    try:
        cur = con.cursor()
        # Luăm evenimentele viitoare (sau toate, depinde cum vrei)
        # Aici luăm tot și filtrăm în frontend sau punem WHERE data_start >= NOW()
        cur.execute("SELECT * FROM calendar_club ORDER BY data_start ASC")
        rows = cur.fetchall()

        events = []
        for r in rows:
            events.append({
                "id": r['id'],
                "titlu": r['titlu'],
                "start": str(r['data_start']),  # Format ISO pt calendar frontend
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


# --- 2. ADĂUGARE EVENIMENT (Doar Admin/Antrenor) ---
@calendar_club_bp.post("/api/calendar/evenimente")
@token_required
@admin_required  # Sau permite și antrenorilor
def add_event():
    data = request.get_json() or {}
    titlu = data.get("titlu")
    start = data.get("start")  # Așteptăm format YYYY-MM-DD HH:MM
    end = data.get("end")
    locatie = data.get("locatie")
    descriere = data.get("descriere")
    tip = data.get("tip") or "General"

    if not titlu or not start:
        return jsonify({"status": "error", "message": "Titlul și Data de start sunt obligatorii"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO calendar_club (titlu, data_start, data_sfarsit, locatie, descriere, tip_eveniment)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (titlu, start, end, locatie, descriere, tip))
        con.commit()
        return jsonify({"status": "success", "message": "Eveniment adăugat!"}), 201
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 3. ȘTERGERE EVENIMENT ---
@calendar_club_bp.delete("/api/calendar/evenimente/<int:event_id>")
@token_required
@admin_required
def delete_event(event_id):
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