from flask import Blueprint, jsonify
from ..config import get_conn, DB_PATH

numar_inscrisi_bp = Blueprint('numar_inscrisi', __name__)

@numar_inscrisi_bp.get('/api/numar_inscrisi/<nume_concurs>')
def numar_inscrisi(nume_concurs: str):
    try:
        con = get_conn()
        row = con.execute(
            "SELECT COUNT(*) AS cnt FROM inscrieri_concursuri WHERE concurs = ?",
            (nume_concurs,)
        ).fetchone()
        return jsonify({"nr": (row["cnt"] if row else 0)})
    except Exception as e:
        # păstrăm format minimal chiar și pe eroare
        return jsonify({"nr": 0, "error": str(e)}), 500


@numar_inscrisi_bp.get('/api/inscrisi_concurs/<nume_concurs>')
def inscrisi_concurs(nume_concurs: str):
    try:
        con = get_conn()
        rows = con.execute("""
            SELECT nume, data_nasterii, categorie_varsta, grad_centura, greutate, probe, gen
            FROM inscrieri_concursuri
            WHERE concurs = ?
            ORDER BY id DESC
        """, (nume_concurs,)).fetchall()

        rezultat = [{
            "nume": r["nume"],
            "data_nasterii": r["data_nasterii"],
            "categorie_varsta": r["categorie_varsta"],
            "grad_centura": r["grad_centura"],
            "greutate": r["greutate"],
            "probe": r["probe"],
            "gen": r["gen"],
        } for r in rows]

        return jsonify(rezultat)
    except Exception as e:
        # pe această rută ai returnat listă; în caz de eroare returnăm listă goală + mesaj
        return jsonify({"status": "error", "message": str(e), "items": []}), 500
