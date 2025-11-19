# backend/users/toti_userii.py
from flask import Blueprint, jsonify, request
from ..config import get_conn
from psycopg2 import errors

toti_userii_bp = Blueprint("toti_userii", __name__)


@toti_userii_bp.get("/api/users")
def get_all_users():
    with get_conn() as con:
        with con.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    username,
                    email,
                    rol,
                    COALESCE(nume_complet, username) AS display_name
                FROM utilizatori
                ORDER BY id DESC
            """)
            rows = cur.fetchall()

    # rows este listă de dict-uri
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
def sterge_utilizator(username: str):
    admin = (request.args.get("admin_username") or "").strip()
    if not admin:
        return jsonify({"status": "error", "message": "Lipsește numele adminului"}), 401

    try:
        with get_conn() as con:
            with con.cursor() as cur:
                # verificăm că requester-ul e admin
                cur.execute(
                    "SELECT rol FROM utilizatori WHERE username = %s LIMIT 1",
                    (admin,),
                )
                admin_row = cur.fetchone()
                if not admin_row or (admin_row["rol"] or "").lower() != "admin":
                    return jsonify({
                        "status": "error",
                        "message": "Doar adminii pot șterge utilizatori"
                    }), 403

                cur.execute(
                    "DELETE FROM utilizatori WHERE username = %s",
                    (username,),
                )
                if cur.rowcount == 0:
                    return jsonify({
                        "status": "error",
                        "message": "Utilizator inexistent"
                    }), 404

        return jsonify({
            "status": "success",
            "message": "Utilizator șters",
            "username": username,
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@toti_userii_bp.patch("/api/users/<int:user_id>")
def update_user(user_id: int):
    data = request.get_json(silent=True) or {}
    admin = (data.get("admin_username") or "").strip()
    new_username = (data.get("username") or "").strip()
    new_email = (data.get("email") or "").strip()

    if not admin:
        return jsonify({"status": "error", "message": "Lipsește numele adminului"}), 401
    if not new_username or not new_email:
        return jsonify({"status": "error", "message": "Nume și email sunt obligatorii"}), 400

    try:
        with get_conn() as con:
            with con.cursor() as cur:
                cur.execute(
                    "SELECT rol FROM utilizatori WHERE username = %s LIMIT 1",
                    (admin,),
                )
                admin_row = cur.fetchone()
                if not admin_row or (admin_row["rol"] or "").lower() != "admin":
                    return jsonify({
                        "status": "error",
                        "message": "Doar adminii pot modifica utilizatori"
                    }), 403

                cur.execute("""
                    UPDATE utilizatori
                       SET username = %s,
                           email = %s
                     WHERE id = %s
                """, (new_username, new_email, user_id))
                if cur.rowcount == 0:
                    return jsonify({
                        "status": "error",
                        "message": "Utilizator inexistent"
                    }), 404

        return jsonify({"status": "success", "message": "Utilizator actualizat"}), 200

    except errors.UniqueViolation:
        # dacă ai activat autocommit False, trebuie rollback:
        # con.rollback()
        return jsonify({
            "status": "error",
            "message": "Username sau email deja folosit"
        }), 409
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
