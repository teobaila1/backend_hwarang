# backend/users/toti_userii.py
from psycopg2 import errors
from flask import Blueprint, jsonify, request
from ..config import get_conn
# Importăm decoratorii de securitate
from ..accounts.decorators import token_required, admin_required

toti_userii_bp = Blueprint("toti_userii", __name__)

@toti_userii_bp.get("/api/users")
@token_required  # <-- Paznic: Trebuie să fii logat
@admin_required  # <-- Paznic: Trebuie să fii Admin
def get_all_users():
    # Nu mai verificăm manual. Dacă a ajuns aici, e sigur Admin.
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
    # Nu mai avem nevoie de admin_username din body, îl știm din token
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