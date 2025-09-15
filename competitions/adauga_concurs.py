from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH  # o singură sursă pentru DB

adauga_concurs_bp = Blueprint('adauga_concurs', __name__)

@adauga_concurs_bp.post('/api/adauga_concurs')
def adauga_concurs():
    data = request.get_json(silent=True) or {}
    nume = (data.get('nume') or '').strip()
    perioada = (data.get('perioada') or '').strip()
    locatie = (data.get('locatie') or '').strip()

    if not nume or not perioada or not locatie:
        return jsonify({"status": "error", "message": "Câmpuri obligatorii: nume, perioada, locatie"}), 400

    try:
        con = get_conn()

        # (opțional) prevenim duplicatele pe (nume, perioada, locatie)
        dup = con.execute(
            """SELECT 1 FROM concursuri
               WHERE LOWER(nume)=LOWER(?) AND perioada=? AND LOWER(locatie)=LOWER(?)
               LIMIT 1""",
            (nume, perioada, locatie)
        ).fetchone()
        if dup:
            return jsonify({"status": "error", "message": "Concurs deja existent"}), 409

        con.execute(
            "INSERT INTO concursuri (nume, perioada, locatie) VALUES (?, ?, ?)",
            (nume, perioada, locatie)
        )
        con.commit()

        return jsonify({"status": "success", "message": "Concurs adăugat"}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
