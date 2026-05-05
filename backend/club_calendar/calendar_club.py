from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

calendar_club_bp = Blueprint('calendar_club', __name__)

def _ensure_calendar_table():
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                # Am adăugat id_concurs_asociat pentru a face legătura cu tabela veche
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS calendar_club (
                        id SERIAL PRIMARY KEY,
                        titlu TEXT NOT NULL,
                        data_start TIMESTAMP NOT NULL,
                        data_sfarsit TIMESTAMP,
                        locatie TEXT,
                        descriere TEXT,
                        tip_eveniment TEXT DEFAULT 'Competitie',
                        id_concurs_asociat INTEGER 
                    )
                """)
                # Asigurăm adăugarea coloanei dacă tabela există deja
                cur.execute("""
                    ALTER TABLE calendar_club 
                    ADD COLUMN IF NOT EXISTS id_concurs_asociat INTEGER;
                """)
    except Exception as e:
        print(f"Eroare tabel club_calendar: {e}")

_ensure_calendar_table()

@calendar_club_bp.get("/api/calendar/evenimente")
@token_required 
def get_events():
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
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
                "tip": r['tip_eveniment'],
                "id_concurs_asociat": r['id_concurs_asociat'] # Trimitem id-ul către frontend
            })
        return jsonify(events), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@calendar_club_bp.post("/api/calendar/evenimente")
@token_required
def add_event():
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403

    data = request.get_json() or {}
    titlu = data.get("titlu")
    start = data.get("start")
    end = data.get("end")
    locatie = data.get("locatie")
    descriere = data.get("descriere")
    tip = data.get("tip")

    if not titlu or not start:
        return jsonify({"status": "error", "message": "Date obligatorii lipsă"}), 400

    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                concurs_nou_id = None
                
                # 1. VERIFICĂM: Este competiție? DOAR ATUNCI îl băgăm în tabela `concursuri`
                if tip == "Competitie":
                    perioada = f"{start[:10]}"
                    if end:
                        perioada = f"{start[:10]} - {end[:10]}"

                    cur.execute("""
                        INSERT INTO concursuri (nume, perioada, locatie, cere_inaltime, inscrieri_deschise)
                        VALUES (%s, %s, %s, %s, %s) RETURNING id
                    """, (titlu, perioada, locatie, False, True)) 
                    
                    concurs_nou_id = cur.fetchone()[0]

                # 2. Creăm evenimentul în calendar. 
                # Dacă NU a fost competiție, id_concurs_asociat va fi automat NULL (gol).
                cur.execute("""
                    INSERT INTO calendar_club (titlu, data_start, data_sfarsit, locatie, descriere, tip_eveniment, id_concurs_asociat)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (titlu, start, end, locatie, descriere, tip, concurs_nou_id))
                
        return jsonify({"status": "success"}), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Eroare internă de server"}), 500


@calendar_club_bp.delete("/api/calendar/evenimente/<int:event_id>")
@token_required
def delete_event(event_id):
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                # Opțional: Poți șterge și din tabela `concursuri` dacă vrei, 
                # dar momentan ștergem doar din calendar să fim siguri.
                cur.execute("DELETE FROM calendar_club WHERE id = %s", (event_id,))
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@calendar_club_bp.put("/api/calendar/evenimente/<int:event_id>")
@token_required
def edit_event(event_id):
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403
    data = request.get_json() or {}
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                cur.execute("""
                    UPDATE calendar_club 
                    SET titlu = %s, data_start = %s, data_sfarsit = %s, 
                        locatie = %s, descriere = %s, tip_eveniment = %s
                    WHERE id = %s
                """, (data.get("titlu"), data.get("start"), data.get("end"),
                      data.get("locatie"), data.get("descriere"), data.get("tip"), event_id))
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500