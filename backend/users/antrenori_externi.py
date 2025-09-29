# backend/users/antrenori_externi.py
from flask import Blueprint, jsonify
from ..config import get_conn, DB_PATH

antrenori_externi_bp = Blueprint("antrenori_externi", __name__)

@antrenori_externi_bp.get("/api/antrenori_externi")
def get_antrenori_externi():
    try:
        con = get_conn()

        # 1) toți antrenorii externi
        users = con.execute("""
            SELECT id, username, email
            FROM utilizatori
            WHERE LOWER(rol) = 'antrenorextern'
            ORDER BY id DESC
        """).fetchall()

        ids = [u["id"] for u in users]
        concursuri_per_user = {uid: [] for uid in ids}

        # 2) permisiuni doar pentru userii găsiți (evităm N+1)
        if ids:
            placeholders = ",".join("?" for _ in ids)
            rows = con.execute(f"""
                SELECT cp.user_id AS uid, c.nume AS nume
                FROM concursuri_permisiuni cp
                JOIN concursuri c ON c.id = cp.concurs_id
                WHERE cp.user_id IN ({placeholders})
                ORDER BY c.id DESC
            """, ids).fetchall()

            for r in rows:
                concursuri_per_user[r["uid"]].append(r["nume"])

        rezultat = [{
            "id": u["id"],
            "username": u["username"],
            "email": u["email"],
            "concursuri_permise": concursuri_per_user.get(u["id"], [])
        } for u in users]

        return jsonify(rezultat)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
