import json
from datetime import datetime
from flask import request, jsonify, Blueprint
from ..accounts.decorators import token_required
from ..config import get_conn

antrenor_dashboard_copii_parinti_bp = Blueprint("antrenor_dashboard_copii_parinti", __name__)


def _calculate_age(dob):
    if not dob: return 0
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d")
        except:
            return 0
    today = datetime.now()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


@antrenor_dashboard_copii_parinti_bp.post("/api/antrenor_dashboard_data")
@token_required
def antrenor_dashboard_data():
    data = request.get_json(silent=True) or {}
    trainer_username = (data.get("username") or "").strip()
    if not trainer_username:
        return jsonify({"status": "error", "message": "Lipsă username antrenor."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Găsim ID-ul antrenorului
        cur.execute("SELECT id, rol FROM utilizatori WHERE username = %s", (trainer_username,))
        trainer_row = cur.fetchone()
        if not trainer_row:
            return jsonify({"status": "success", "date": []}), 200

        trainer_id = trainer_row['id']
        trainer_rol = trainer_row['rol'].lower()

        # 2. Găsim grupele gestionate de acest antrenor
        # Dacă e ADMIN, le vede pe toate. Dacă e ANTRENOR, doar pe ale lui.
        if trainer_rol == 'admin':
            cur.execute("SELECT id, nume FROM grupe ORDER BY nume ASC")
        else:
            cur.execute("SELECT id, nume FROM grupe WHERE id_antrenor = %s ORDER BY nume ASC", (trainer_id,))

        grupe_rows = cur.fetchall()

        if not grupe_rows:
            return jsonify({"status": "success", "date": []}), 200

        results = []

        # 3. Pentru fiecare grupă, luăm sportivii (copii + adulți)
        for gr in grupe_rows:
            g_id = gr['id']
            g_nume = gr['nume']

            # A. COPII
            cur.execute("""
                SELECT c.id, c.nume, c.data_nasterii, c.gen,
                       u.id as pid, u.username as puser, u.nume_complet as pfull, u.email as pemail
                FROM sportivi_pe_grupe sg
                JOIN copii c ON sg.id_sportiv_copil = c.id
                JOIN utilizatori u ON c.id_parinte = u.id
                WHERE sg.id_grupa = %s
            """, (g_id,))
            kids_rows = cur.fetchall()

            # B. SPORTIVI ADULȚI
            cur.execute("""
                SELECT u.id, u.nume_complet, u.username, u.data_nasterii, u.gen, u.email
                FROM sportivi_pe_grupe sg
                JOIN utilizatori u ON sg.id_sportiv_user = u.id
                WHERE sg.id_grupa = %s
            """, (g_id,))
            adults_rows = cur.fetchall()

            # Procesăm lista combinată
            lista_copii = []

            # Adăugăm Copiii
            for k in kids_rows:
                lista_copii.append({
                    "id": k['id'],  # UUID string
                    "nume": k['nume'],
                    "varsta": _calculate_age(k['data_nasterii']),
                    "gen": k['gen'] or "—",
                    "grupa": g_nume,
                    "tip": "copil",
                    "_parinte_info": {
                        "id": k['pid'],
                        "display": k['pfull'] or k['puser'],
                        "email": k['pemail']
                    }
                })

            # Adăugăm Adulții
            for a in adults_rows:
                display_name = a['nume_complet'] or a['username']
                lista_copii.append({
                    "id": str(a['id']),  # ID numeric convertit la string
                    "nume": display_name,
                    "varsta": _calculate_age(a['data_nasterii']),
                    "gen": a['gen'] or "—",
                    "grupa": g_nume,
                    "tip": "sportiv",
                    "_parinte_info": {
                        "id": a['id'],
                        "display": f"{display_name} (Sportiv)",
                        "email": a['email']
                    }
                })

            # Grupăm după "Părinte" pentru afișare (Așa cere frontend-ul vechi)
            # Frontend-ul se așteaptă la {grupa: "X", parinte: {...}, copii: [...]}
            # Trebuie să regrupăm lista plată de mai sus.

            # Mapare: ParinteID -> {info_parinte, lista_copii}
            map_familii = {}

            for elev in lista_copii:
                pid = elev["_parinte_info"]["id"]
                if pid not in map_familii:
                    map_familii[pid] = {
                        "parinte": {
                            "id": pid,
                            "display": elev["_parinte_info"]["display"],
                            "email": elev["_parinte_info"]["email"],
                            "username": "..."
                        },
                        "copii": []
                    }
                # Curățăm obiectul elev de cheia _parinte_info ca să nu o trimitem dublu
                clean_elev = {k: v for k, v in elev.items() if k != "_parinte_info"}
                map_familii[pid]["copii"].append(clean_elev)

            # Construim rezultatul final pentru această grupă
            for pid, val in map_familii.items():
                results.append({
                    "grupa": g_nume,
                    "parinte": val["parinte"],
                    "copii": val["copii"]
                })

        # Sortare finală
        def group_key(item):
            import re
            name = item['grupa']
            m = re.search(r"(\d+)", name or "")
            return (int(m.group(1)) if m else 9999, (name or "").lower())

        results.sort(key=lambda x: (group_key(x), x['parinte']['display']))

        return jsonify({"status": "success", "date": results}), 200

    except Exception as e:
        print(f"Eroare SQL Dashboard: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Endpoint auxiliar pentru părinți (rămâne compatibil)
@antrenor_dashboard_copii_parinti_bp.route("/api/copiii_mei", methods=["POST"])
@token_required
def copiii_mei():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username: return jsonify({"status": "error"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        # Luăm ID părinte
        cur.execute("SELECT id FROM utilizatori WHERE username = %s", (username,))
        p_row = cur.fetchone()
        if not p_row: return jsonify({"status": "error", "message": "User not found"}), 404

        pid = p_row['id']

        # Luăm copiii din tabelul COPII
        cur.execute("SELECT id, nume, data_nasterii, gen, grupa_text FROM copii WHERE id_parinte = %s", (pid,))
        rows = cur.fetchall()

        copii_list = []
        for r in rows:
            copii_list.append({
                "id": r['id'],
                "nume": r['nume'],
                "varsta": _calculate_age(r['data_nasterii']),
                "gen": r['gen'],
                "grupa": r['grupa_text']  # Sau facem JOIN cu grupe dacă vrem numele oficial
            })

        return jsonify({"status": "success", "copii": copii_list})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500