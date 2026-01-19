from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required, admin_required

modifica_rol_bp = Blueprint('modifica_rol', __name__)


@modifica_rol_bp.patch('/api/admin/modifica_rol')
@token_required
@admin_required
def modifica_rol():
    data = request.get_json(silent=True) or {}
    target_username = data.get('username')
    new_role = data.get('rol')  # Ex: 'Antrenor', 'Admin', 'Sportiv', 'Parinte'

    if not target_username or not new_role:
        return jsonify({"status": "error", "message": "Lipsesc datele."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Găsim ID-ul userului
        cur.execute("SELECT id FROM utilizatori WHERE username = %s", (target_username,))
        row = cur.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "User not found"}), 404

        user_id = row['id']

        # 2. Actualizăm tabelul ROLURI
        # Verificăm dacă are deja intrare în roluri
        cur.execute("SELECT id FROM roluri WHERE id_user = %s", (user_id,))
        if cur.fetchone():
            cur.execute("UPDATE roluri SET rol = %s WHERE id_user = %s", (new_role, user_id))
        else:
            cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, %s)", (user_id, new_role))

        # 3. Actualizăm și tabelul vechi pentru compatibilitate (opțional, dar recomandat)
        cur.execute("UPDATE utilizatori SET rol = %s WHERE id = %s", (new_role, user_id))

        con.commit()
        return jsonify({"status": "success", "message": f"Rol schimbat în {new_role}"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500