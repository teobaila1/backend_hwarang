from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH  # o singură sursă pentru DB

concurs_permis_antrenori_externi_bp = Blueprint("concurs_permis_antrenori_externi", __name__)

# (opțional) debug:
# print(f"[BOOT] concurs_permis_antrenori_externi folosește DB: {DB_PATH}")

@concurs_permis_antrenori_externi_bp.post("/api/concurs_permis")
def concurs_permis():
    """Returnează concursurile permise pentru un antrenor extern (după username)."""
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    if not username:
        return jsonify({"status": "error", "message": "Lipsă username"}), 400

    try:
        con = get_conn()
        rows = con.execute("""
            SELECT c.nume, c.perioada, c.locatie
            FROM concursuri c
            JOIN concursuri_permisiuni cp ON c.id = cp.concurs_id
            JOIN utilizatori u ON u.id = cp.user_id
            WHERE u.username = ?
        """, (username,)).fetchall()

        concursuri = [{"nume": r["nume"], "perioada": r["perioada"], "locatie": r["locatie"]} for r in rows]
        return jsonify({"status": "success", "concursuri": concursuri})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@concurs_permis_antrenori_externi_bp.get("/api/toate_concursurile")
def toate_concursurile():
    """Listă simplă cu toate concursurile (id, nume, perioada)."""
    try:
        con = get_conn()
        rows = con.execute("SELECT id, nume, perioada FROM concursuri ORDER BY id DESC").fetchall()
        concursuri = [{"id": r["id"], "nume": r["nume"], "perioada": r["perioada"]} for r in rows]
        return jsonify({"status": "success", "concursuri": concursuri})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@concurs_permis_antrenori_externi_bp.post("/api/set_permisiuni")
def set_permisiuni():
    """
    Setează permisiunile de concurs pentru un utilizator:
    Body: { "user_id": <int>, "concurs_ids": [<int>, ...] }
    """
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    concurs_ids = data.get("concurs_ids", [])
    if not user_id or not isinstance(concurs_ids, list):
        return jsonify({"status": "error", "message": "Lipsesc user_id sau concurs_ids"}), 400

    try:
        con = get_conn()
        # Șterge toate permisiunile anterioare
        con.execute("DELETE FROM concursuri_permisiuni WHERE user_id = ?", (user_id,))
        # Adaugă noile permisiuni
        con.executemany(
            "INSERT INTO concursuri_permisiuni (user_id, concurs_id) VALUES (?, ?)",
            [(user_id, int(cid)) for cid in concurs_ids]
        )
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@concurs_permis_antrenori_externi_bp.get("/api/get_permisiuni/<username>")
def get_permisiuni_antrenor(username: str):
    """Returnează lista de concurs_id permise pentru antrenorul extern <username>."""
    username = (username or "").strip()
    if not username:
        return jsonify({"status": "error", "message": "Lipsă username"}), 400

    try:
        con = get_conn()
        rows = con.execute("""
            SELECT cp.concurs_id
            FROM concursuri_permisiuni cp
            JOIN utilizatori u ON cp.user_id = u.id
            WHERE u.username = ?
        """, (username,)).fetchall()
        return jsonify([r["concurs_id"] for r in rows])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
