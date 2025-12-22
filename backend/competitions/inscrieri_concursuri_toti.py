from flask import jsonify, Blueprint, request
from ..config import get_conn  # ← o singură sursă pentru DB

inscriere_concurs_toti_bp = Blueprint('inscriere_concurs_toti', __name__)

@inscriere_concurs_toti_bp.get("/api/inscrisi_concursuri")
def inscrisi_concursuri():
    try:
        con = get_conn()
        # --- 1. Adăugat inaltime în SELECT ---
        rows = con.execute("""
            SELECT id, nume, gen, categorie_varsta, grad_centura, greutate, inaltime, probe,
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
            "inaltime": r["inaltime"], # --- 2. Adăugat în răspuns ---
            "probe": r["probe"],
            "concurs": r["concurs"],
            "data_nasterii": r["data_nasterii"],
            "inscris_de": f'{r["username"]} ({r["email"]})'
        } for r in rows]

        return jsonify({"status": "success", "sportivi": sportivi})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@inscriere_concurs_toti_bp.route("/api/update_inscriere/<int:id>", methods=["POST"])
def update_inscriere(id):
    data = request.get_json(silent=True) or {}
    # Lista de câmpuri necesare (inaltime e opțională, deci nu o punem la required strict, dar o folosim la update)
    required = ["nume", "gen", "categorie", "grad", "greutate", "probe", "concurs", "data_nasterii"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"status": "error", "message": f"Lipsesc câmpuri: {', '.join(missing)}"}), 400

    try:
        con = get_conn()
        # --- 3. Actualizăm query-ul de UPDATE cu inaltime ---
        con.execute("""
            UPDATE inscrieri_concursuri
               SET nume = %s, gen = %s, categorie_varsta = %s, grad_centura = %s,
                   greutate = %s, inaltime = %s, probe = %s, concurs = %s, data_nasterii = %s
             WHERE id = %s
        """, (
            data["nume"],
            data["gen"],
            data["categorie"],
            data["grad"],
            data["greutate"],
            data.get("inaltime", ""), # Luăm inaltime, sau gol dacă lipsește
            data["probe"],
            data["concurs"],
            data["data_nasterii"],
            id
        ))
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@inscriere_concurs_toti_bp.delete("/api/delete_inscriere/<int:id>")
def delete_inscriere(id):
    try:
        con = get_conn()
        cur = con.execute("DELETE FROM inscrieri_concursuri WHERE id = %s", (id,))
        con.commit()
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Înscriere inexistentă"}), 404
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500