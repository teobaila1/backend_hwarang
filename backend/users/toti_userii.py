# backend/users/toti_userii.py
import json
from psycopg2 import errors
from flask import Blueprint, jsonify, request
from ..config import get_conn
# Importăm decoratorii de securitate
from ..accounts.decorators import token_required, admin_required

toti_userii_bp = Blueprint("toti_userii", __name__)

# --- Helper pentru a verifica daca ID-ul e numar (Sportiv) ---
def is_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

# ==========================================
#  RUTE EXISTENTE (ADMIN USERS)
# ==========================================

@toti_userii_bp.get("/api/users")
@token_required
@admin_required
def get_all_users():
    with get_conn() as con:
        with con.cursor() as cur:
            cur.execute("""
                SELECT id, username, email, rol, COALESCE(nume_complet, username) AS display_name
                FROM utilizatori ORDER BY id DESC
            """)
            rows = cur.fetchall()

    return jsonify([
        {
            "id": r["id"],
            "username": r["username"],
            "email": r["email"],
            "rol": r["rol"],
            "display_name": r["display_name"],
        }
        for r in rows
    ])

@toti_userii_bp.delete("/api/users/<string:username>")
@token_required
@admin_required
def sterge_utilizator(username: str):
    try:
        with get_conn() as con:
            with con.cursor() as cur:
                cur.execute("DELETE FROM utilizatori WHERE username = %s", (username,))
                if cur.rowcount == 0:
                    return jsonify({"status": "error", "message": "Utilizator inexistent"}), 404

        return jsonify({"status": "success", "message": "Utilizator șters"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@toti_userii_bp.patch("/api/users/<int:user_id>")
@token_required
@admin_required
def update_user(user_id: int):
    data = request.get_json(silent=True) or {}
    new_username = (data.get("username") or "").strip()
    new_email = (data.get("email") or "").strip()

    if not new_username or not new_email:
        return jsonify({"status": "error", "message": "Nume și email sunt obligatorii"}), 400

    try:
        with get_conn() as con:
            with con.cursor() as cur:
                cur.execute("""
                    UPDATE utilizatori
                       SET username = %s,
                           email = %s
                     WHERE id = %s
                """, (new_username, new_email, user_id))
                if cur.rowcount == 0:
                    return jsonify({"status": "error", "message": "Utilizator inexistent"}), 404

        return jsonify({"status": "success", "message": "Utilizator actualizat"}), 200

    except errors.UniqueViolation:
        return jsonify({"status": "error", "message": "Username sau email deja folosit"}), 409
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================
#  RUTA NOUĂ: EDITARE ELEV / SPORTIV
# ==========================================
# Aceasta a fost mutată aici ca să fim siguri că serverul o vede.

@toti_userii_bp.patch('/api/elevi/<string:target_id>')
@token_required
def modifica_elev_universal(target_id):
    """
    Gestionează editarea atât pentru Sportivi (ID numeric) cât și pentru Copii (UUID).
    """
    data = request.get_json(silent=True) or {}

    nume_nou = data.get("nume")
    gen_nou = data.get("gen")
    grupa_noua = data.get("grupa")

    try:
        con = get_conn()
        cur = con.cursor()

        # CAZUL 1: SPORTIV (ID Numeric - ex: '48')
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

            cur.execute(sql, tuple(values))
            con.commit()

            if cur.rowcount == 0:
                return jsonify({"status": "error", "message": "Sportivul nu a fost găsit"}), 404

            return jsonify({"status": "success", "message": "Sportiv actualizat"}), 200

        # CAZUL 2: COPIL (UUID - ex: 'a1b2-c3d4...')
        else:
            # Căutăm părintele
            cur.execute("SELECT id, copii FROM utilizatori WHERE copii IS NOT NULL")
            parents = cur.fetchall()

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

            # Modificăm datele în JSON
            for k in children_list:
                if k.get('id') == target_id:
                    if nume_nou: k['nume'] = nume_nou
                    if gen_nou: k['gen'] = gen_nou
                    if grupa_noua: k['grupa'] = grupa_noua
                    break

            # Salvăm JSON-ul actualizat
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