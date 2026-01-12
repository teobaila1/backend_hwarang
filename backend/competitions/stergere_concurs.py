# backend/competitions/stergere_concurs.py
from flask import Blueprint, jsonify

from ..accounts.decorators import token_required
from ..config import get_conn
import urllib.parse

stergere_concurs_bp = Blueprint('stergere_concurs', __name__)

@stergere_concurs_bp.delete('/api/sterge_concurs/<nume>')
@token_required
@admin_required
def delete_concurs(nume: str):
    decoded_name = (urllib.parse.unquote(nume) or "").strip()
    if not decoded_name:
        return jsonify({"status": "error", "message": "Numele concursului lipsește."}), 400

    try:
        with get_conn() as con:
            with con.cursor() as cur:
                # 1) Căutăm concursul (case-insensitive)
                cur.execute(
                    "SELECT id, nume FROM concursuri WHERE LOWER(nume) = LOWER(%s) LIMIT 1",
                    (decoded_name,),
                )
                row = cur.fetchone()
                if not row:
                    return jsonify({
                        "status": "error",
                        "message": "Concursul nu a fost găsit."
                    }), 404

                concurs_id = row["id"]
                nume_concurs = row["nume"]

                # 2) Ștergem înscrierile aferente (după nume concurs)
                cur.execute(
                    "DELETE FROM inscrieri_concursuri WHERE concurs = %s",
                    (nume_concurs,),
                )

                # 3) Ștergem permisiunile aferente (dacă există tabela)
                cur.execute("""
                    SELECT to_regclass('public.concursuri_permisiuni') AS t
                """)
                tbl = cur.fetchone()
                if tbl and tbl["t"]:
                    cur.execute(
                        "DELETE FROM concursuri_permisiuni WHERE concurs_id = %s",
                        (concurs_id,),
                    )

                # 4) Ștergem concursul
                cur.execute(
                    "DELETE FROM concursuri WHERE id = %s",
                    (concurs_id,),
                )

        return jsonify({
            "status": "success",
            "message": f'Concursul „{nume_concurs}” și înscrierile aferente au fost șterse.'
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
