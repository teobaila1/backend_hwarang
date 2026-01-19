import json
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..accounts.decorators import token_required

editare_elev_bp = Blueprint('editare_elev', __name__)

def is_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

@editare_elev_bp.patch('/api/elevi/<string:target_id>')
@token_required
def modifica_elev(target_id):
    """
    Acest endpoint este 'deștept'.
    1. Dacă target_id e număr (ex: '48') -> Știe că e Sportiv și actualizează tabelul `utilizatori`.
    2. Dacă target_id e UUID (ex: 'a1b2...') -> Știe că e Copil și actualizează JSON-ul părintelui.
    """
    data = request.get_json(silent=True) or {}

    nume_nou = data.get("nume")
    gen_nou = data.get("gen")
    grupa_noua = data.get("grupa")

    try:
        con = get_conn()
        cur = con.cursor() # <--- IMPORTANT: Folosim cursor

        # CAZUL 1: SPORTIV (ID Numeric)
        if is_integer(target_id):
            user_id = int(target_id)

            fields = []
            values = []

            if nume_nou:
                fields.append("nume_complet = %s")
                values.append(nume_nou)
            if gen_nou:
                fields.append("gen = %s")
                values.append(gen_nou)
            if grupa_noua:
                fields.append("grupe = %s")
                values.append(grupa_noua)

            if not fields:
                return jsonify({"status": "success", "message": "Nimic de actualizat"}), 200

            values.append(user_id)
            sql = f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s"

            cur.execute(sql, tuple(values)) # Executăm pe cursor
            con.commit()

            if cur.rowcount == 0:
                return jsonify({"status": "error", "message": "Sportivul nu a fost găsit"}), 404

            return jsonify({"status": "success", "message": "Sportiv actualizat"}), 200

        # CAZUL 2: COPIL (UUID)
        else:
            # Căutăm părintele care are acest copil
            cur.execute("SELECT id, copii FROM utilizatori WHERE copii IS NOT NULL")
            parents = cur.fetchall() # Executăm pe cursor

            parent_found = None
            children_list = []

            for p in parents:
                try:
                    kids = json.loads(p['copii'] or "[]")
                    for k in kids:
                        if k.get('id') == target_id:
                            parent_found = p
                            children_list = kids
                            break
                except:
                    continue
                if parent_found:
                    break

            if not parent_found:
                return jsonify({"status": "error", "message": "Elevul nu a fost găsit"}), 404

            # Actualizăm datele copilului
            for k in children_list:
                if k.get('id') == target_id:
                    if nume_nou: k['nume'] = nume_nou
                    if gen_nou: k['gen'] = gen_nou
                    if grupa_noua: k['grupa'] = grupa_noua
                    break

            # Salvăm înapoi în DB
            cur.execute(
                "UPDATE utilizatori SET copii = %s WHERE id = %s",
                (json.dumps(children_list, ensure_ascii=False), parent_found['id'])
            )
            con.commit()

            return jsonify({"status": "success", "message": "Elev actualizat"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if 'con' in locals() and con:
            con.close()