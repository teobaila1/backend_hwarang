from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH
import json as _json

evidenta_plati_bp = Blueprint("evidenta_plati", __name__)

# --- helpers --------------------------------------------------------------

def ensure_tables():
    """Creează tabela plati dacă nu există."""
    con = get_conn()
    con.execute("""
        CREATE TABLE IF NOT EXISTS plati (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parinte_id INTEGER NOT NULL,
            copil_nume TEXT NOT NULL,
            luna TEXT,
            suma REAL,
            tip_plata TEXT,
            status TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()

def _safe_load_children(copii_json):
    if not copii_json:
        return []
    try:
        return _json.loads(copii_json)
    except Exception:
        return []

def get_parinte_id_by_copil(copil_nume: str):
    """Mapează numele copilului (case-insensitive) -> parinte_id."""
    if not copil_nume:
        return None
    target = copil_nume.strip().upper()

    con = get_conn()
    rows = con.execute("SELECT id, copii FROM utilizatori WHERE LOWER(rol) = 'parinte'").fetchall()
    for r in rows:
        for copil in _safe_load_children(r["copii"]):
            if (copil.get("nume") or "").strip().upper() == target:
                return r["id"]
    return None

# --- routes ---------------------------------------------------------------

@evidenta_plati_bp.get("/api/plati/filtrate")
def get_plati_filtrate():
    """
    Combina:
      - toate plățile existente (join cu numele părintelui),
      - cu „copiii fără plăți” (marcați 'status': 'neplatit').
    Include:
      - parinte_nume    -> username
      - parinte_display -> COALESCE(nume_complet, username)
    """
    try:
        ensure_tables()
        con = get_conn()

        # Plăți existente (cu username și nume de afișat)
        rows = con.execute("""
            SELECT
              p.*,
              u.username AS parinte_nume,
              COALESCE(u.nume_complet, u.username) AS parinte_display
            FROM plati p
            JOIN utilizatori u ON u.id = p.parinte_id
            ORDER BY p.id DESC
        """).fetchall()
        plati_existente = [dict(r) for r in rows]

        # Părinți + copiii lor (pentru a completa rândurile 'neplătit')
        parinti = con.execute("""
            SELECT username,
                   COALESCE(nume_complet, username) AS parinte_display,
                   copii
            FROM utilizatori
            WHERE LOWER(rol) = 'parinte' AND copii IS NOT NULL
        """).fetchall()

        copii_neplatiti = []
        for p in parinti:
            username = p["username"]
            disp = p["parinte_display"]
            for copil in _safe_load_children(p["copii"]):
                copil_nume = (copil.get("nume") or "").strip()
                if not copil_nume:
                    continue
                # dacă NU există vreo plată pentru acest copil (indiferent de lună)
                if not any((pe.get("copil_nume") or "").strip().upper() == copil_nume.upper()
                           for pe in plati_existente):
                    copii_neplatiti.append({
                        "copil_nume": copil_nume,
                        "parinte_nume": username,
                        "parinte_display": disp,
                        "luna": None,
                        "suma": None,
                        "tip_plata": None,
                        "status": "neplatit"
                    })

        return jsonify(plati_existente + copii_neplatiti)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.get("/api/plati")
def get_plati():
    try:
        ensure_tables()
        con = get_conn()
        rows = con.execute("""
            SELECT
              p.*,
              u.username AS parinte_nume,
              COALESCE(u.nume_complet, u.username) AS parinte_display
            FROM plati p
            JOIN utilizatori u ON u.id = p.parinte_id
            ORDER BY p.id DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.post("/api/plati")
def add_plata():
    data = request.get_json(silent=True) or {}
    copil_nume = (data.get("copil_nume") or "").strip()
    luna = (data.get("luna") or "").strip().lower()
    suma = data.get("suma")
    tip_plata = data.get("tip_plata")
    status = data.get("status")

    if not copil_nume:
        return jsonify({"error": "Lipsește copil_nume"}), 400

    parinte_id = get_parinte_id_by_copil(copil_nume)
    if not parinte_id:
        return jsonify({"error": "Parinte necunoscut pentru copilul dat"}), 400

    try:
        ensure_tables()
        con = get_conn()

        # Dacă există deja o plată pentru același copil + lună -> UPDATE
        existing = con.execute("""
            SELECT id FROM plati
            WHERE UPPER(copil_nume) = UPPER(?) AND LOWER(luna) = LOWER(?)
            LIMIT 1
        """, (copil_nume, luna)).fetchone()

        if existing:
            con.execute("""
                UPDATE plati
                   SET suma = ?, tip_plata = ?, status = ?, parinte_id = ?
                 WHERE id = ?
            """, (suma, tip_plata, status, parinte_id, existing["id"]))
        else:
            con.execute("""
                INSERT INTO plati (parinte_id, copil_nume, luna, suma, tip_plata, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (parinte_id, copil_nume, luna, suma, tip_plata, status))

        con.commit()
        return jsonify({"message": "OK"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.put("/api/plati/<int:id>")
def update_plata(id):
    # dacă vine -1 din UI, tratăm ca create
    data = request.get_json(silent=True) or {}

    try:
        ensure_tables()
        con = get_conn()

        exista = con.execute("SELECT id FROM plati WHERE id = ?", (id,)).fetchone()

        if exista:
            con.execute("""
                UPDATE plati
                   SET copil_nume = ?, luna = ?, suma = ?, tip_plata = ?, status = ?
                 WHERE id = ?
            """, (
                data.get("copil_nume"),
                data.get("luna"),
                data.get("suma"),
                data.get("tip_plata"),
                data.get("status"),
                id
            ))
        else:
            parinte_id = get_parinte_id_by_copil(data.get("copil_nume"))
            if not parinte_id:
                return jsonify({"error": "Parinte necunoscut pentru copilul dat"}), 400
            con.execute("""
                INSERT INTO plati (parinte_id, copil_nume, luna, suma, tip_plata, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                parinte_id,
                data.get("copil_nume"),
                data.get("luna"),
                data.get("suma"),
                data.get("tip_plata"),
                data.get("status")
            ))

        con.commit()
        return jsonify({"message": "OK"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.delete("/api/plati/<int:id>")
def delete_plata(id):
    try:
        ensure_tables()
        con = get_conn()
        con.execute("DELETE FROM plati WHERE id = ?", (id,))
        con.commit()
        return jsonify({"message": "Plată ștearsă"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
