from flask import jsonify, Blueprint, request
from ..config import get_conn, DB_PATH  # ← o singură sursă pentru DB

inscriere_concurs_toti_bp = Blueprint('inscriere_concurs_toti', __name__)

# (opțional) vezi în consolă ce DB folosește acest modul
print(f"[BOOT] inscrieri_concursuri_toti folosește DB: {DB_PATH}")

@inscriere_concurs_toti_bp.get("/api/inscrisi_concursuri")
def inscrisi_concursuri():
    try:
        con = get_conn()
        rows = con.execute("""
            SELECT id, nume, gen, categorie_varsta, grad_centura, greutate, probe,
                   concurs, data_nasterii, username, email
            FROM inscrieri_concursuri
            ORDER BY id DESC
        """).fetchall()

        sportivi = [{
            "id": r["id"],
            "nume": r["nume"],
            "gen": r["gen"],
            "categorie": r["categorie_varsta"],
            "grad": r["grad_centura"],
            "greutate": r["greutate"],
            "probe": r["probe"],
            "concurs": r["concurs"],
            "data_nasterii": r["data_nasterii"],
            "inscris_de": f'{r["username"]} ({r["email"]})'
        } for r in rows]

        return jsonify({"status": "success", "sportivi": sportivi})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# Păstrez endpoint-ul tău (POST), dar ideal aici ar fi PATCH.
@inscriere_concurs_toti_bp.route("/api/update_inscriere/<int:id>", methods=["POST"])
def update_inscriere(id):
    data = request.get_json(silent=True) or {}
    required = ["nume", "gen", "categorie", "grad", "greutate", "probe", "concurs", "data_nasterii"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"status": "error", "message": f"Lipsesc câmpuri: {', '.join(missing)}"}), 400

    try:
        con = get_conn()
        con.execute("""
            UPDATE inscrieri_concursuri
               SET nume = ?, gen = ?, categorie_varsta = ?, grad_centura = ?,
                   greutate = ?, probe = ?, concurs = ?, data_nasterii = ?
             WHERE id = ?
        """, (
            data["nume"], data["gen"], data["categorie"], data["grad"],
            data["greutate"], data["probe"], data["concurs"], data["data_nasterii"], id
        ))
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# Păstrez ruta ta, dar ideal ar fi DELETE /api/inscriere/<id>
@inscriere_concurs_toti_bp.delete("/api/delete_inscriere/<int:id>")
def delete_inscriere(id):
    try:
        con = get_conn()
        cur = con.execute("DELETE FROM inscrieri_concursuri WHERE id = ?", (id,))
        con.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Înscriere inexistentă"}), 404
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
