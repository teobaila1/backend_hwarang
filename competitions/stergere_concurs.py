from flask import Blueprint, jsonify
from ..config import get_conn, DB_PATH
import urllib.parse

stergere_concurs_bp = Blueprint('stergere_concurs', __name__)

@stergere_concurs_bp.delete('/api/sterge_concurs/<nume>')
def delete_concurs(nume: str):
    decoded_name = (urllib.parse.unquote(nume) or "").strip()
    if not decoded_name:
        return jsonify({"status": "error", "message": "Numele concursului lipsește."}), 400

    try:
        con = get_conn()

        # 1) Căutăm concursul (case-insensitive)
        row = con.execute(
            "SELECT id, nume FROM concursuri WHERE LOWER(nume) = LOWER(?) LIMIT 1",
            (decoded_name,)
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Concursul nu a fost găsit."}), 404

        concurs_id = row["id"]

        # 2) Ștergem înscrierile aferente (după nume concurs)
        con.execute(
            "DELETE FROM inscrieri_concursuri WHERE concurs = ?",
            (row["nume"],)
        )

        # 3) (opțional) Ștergem permisiunile aferente (dacă există tabela)
        tbl = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='concursuri_permisiuni'"
        ).fetchone()
        if tbl:
            con.execute(
                "DELETE FROM concursuri_permisiuni WHERE concurs_id = ?",
                (concurs_id,)
            )

        # 4) Ștergem concursul
        con.execute("DELETE FROM concursuri WHERE id = ?", (concurs_id,))
        con.commit()

        return jsonify({
            "status": "success",
            "message": f'Concursul „{row["nume"]}” și înscrierile aferente au fost șterse.'
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
