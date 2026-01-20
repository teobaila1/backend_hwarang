from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required, admin_required

modifica_rol_bp = Blueprint('modifica_rol', __name__)


@modifica_rol_bp.route('/api/modifica-rol', methods=['POST', 'PATCH'])
@modifica_rol_bp.route('/api/modifica_rol', methods=['POST', 'PATCH'])
@token_required
@admin_required
def modifica_rol():
    data = request.get_json(silent=True) or {}

    print(f"\n[DEBUG ROL] Date primite: {data}")

    # 1. Extragem Username-ul țintă
    target_username = (
            data.get('username') or
            data.get('target_username') or
            data.get('user')
    )

    # 2. Extragem Rolul Nou (AICI ESTE FIX-UL)
    new_role = (
            data.get('rol') or
            data.get('role') or
            data.get('rol_nou') or  # <--- ASTA LIPSEA! Frontend-ul trimite 'rol_nou'
            data.get('new_role') or
            data.get('newRole')
    )

    if not target_username or not new_role:
        print(f"[DEBUG ERROR] Date incomplete! User={target_username}, Rol={new_role}")
        return jsonify({
            "status": "error",
            "message": f"Lipsesc datele. Am primit: {data}"
        }), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 3. Găsim ID-ul userului
        cur.execute("SELECT id FROM utilizatori WHERE LOWER(username) = LOWER(%s)", (target_username,))
        row = cur.fetchone()
        if not row:
            return jsonify({"status": "error", "message": f"Utilizatorul {target_username} nu există."}), 404

        user_id = row['id']

        # 4. Actualizăm sau Inserăm în tabelul ROLURI
        cur.execute("SELECT id FROM roluri WHERE id_user = %s", (user_id,))
        if cur.fetchone():
            cur.execute("UPDATE roluri SET rol = %s WHERE id_user = %s", (new_role, user_id))
        else:
            cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, %s)", (user_id, new_role))

        # 5. Actualizăm și tabelul principal (backup)
        cur.execute("UPDATE utilizatori SET rol = %s WHERE id = %s", (new_role, user_id))

        con.commit()
        return jsonify({"status": "success", "message": f"Rol schimbat cu succes în {new_role}."}), 200

    except Exception as e:
        con.rollback()
        print(f"[SQL ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()