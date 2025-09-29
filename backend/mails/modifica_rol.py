from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH  # o singură sursă pentru DB

modifica_rol_bp = Blueprint("modifica_rol", __name__)

@modifica_rol_bp.post("/api/modifica-rol")
def modifica_rol():
    data = request.get_json(silent=True) or {}
    admin_username  = (data.get("admin_username")  or "").strip()
    target_username = (data.get("target_username") or "").strip()
    rol_nou         = (data.get("rol_nou")         or "").strip()

    if not admin_username or not target_username or not rol_nou:
        return jsonify({"status": "error", "message": "Date incomplete"}), 400

    try:
        con = get_conn()

        # 1) verifică dacă cererea vine de la un admin
        admin = con.execute(
            "SELECT rol FROM utilizatori WHERE username = ? LIMIT 1",
            (admin_username,)
        ).fetchone()
        if not admin or (admin["rol"] or "").lower() != "admin":
            return jsonify({"status": "error", "message": "Doar adminii pot modifica roluri"}), 403

        # 2) verifică dacă ținta există
        target = con.execute(
            "SELECT id, rol FROM utilizatori WHERE username = ? LIMIT 1",
            (target_username,)
        ).fetchone()
        if not target:
            return jsonify({"status": "error", "message": "Utilizator țintă inexistent"}), 404

        # 3) aplică modificarea (dacă e diferită)
        if (target["rol"] or "") == rol_nou:
            return jsonify({"status": "success", "message": "Rolul este deja setat"}), 200

        con.execute(
            "UPDATE utilizatori SET rol = ? WHERE id = ?",
            (rol_nou, target["id"])
        )
        con.commit()

        return jsonify({
            "status": "success",
            "message": "Rol actualizat cu succes",
            "user": target_username,
            "rol_vechi": target["rol"],
            "rol_nou": rol_nou
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
