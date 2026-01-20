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

        # 2. Găsim grupele
        if trainer_rol == 'admin':
            cur.execute("SELECT id, nume FROM grupe ORDER BY nume ASC")
        else:
            cur.execute("SELECT id, nume FROM grupe WHERE id_antrenor = %s ORDER BY nume ASC", (trainer_id,))

        grupe_rows = cur.fetchall()

        if not grupe_rows:
            return jsonify({"status": "success", "date": []}), 200

        results = []

        # 3. Procesăm sportivii
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

            # B. ADULȚI
            cur.execute("""
                SELECT u.id, u.nume_complet, u.username, u.data_nasterii, u.gen, u.email
                FROM sportivi_pe_grupe sg
                JOIN utilizatori u ON sg.id_sportiv_user = u.id
                WHERE sg.id_grupa = %s
            """, (g_id,))
            adults_rows = cur.fetchall()

            lista_copii = []

            for k in kids_rows:
                lista_copii.append({
                    "id": k['id'],
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

            for a in adults_rows:
                display_name = a['nume_complet'] or a['username']
                lista_copii.append({
                    "id": str(a['id']),
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
                clean_elev = {k: v for k, v in elev.items() if k != "_parinte_info"}
                map_familii[pid]["copii"].append(clean_elev)

            for pid, val in map_familii.items():
                results.append({
                    "grupa": g_nume,
                    "parinte": val["parinte"],
                    "copii": val["copii"]
                })

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

# AM ȘTERS FUNCȚIA duplicat 'copiii_mei' de aici.
# Acum se va folosi doar cea corectă din parinti.py