from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH
from ..passwords.security import hash_password, check_password  # werkzeug wrappers

autentificare_bp = Blueprint("autentificare", __name__)

@autentificare_bp.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username_or_email = data.get("username") or data.get("email")
    password = data.get("password") or data.get("parola")

    if not username_or_email or not password:
        return jsonify({"status": "error", "message": "Date incomplete"}), 400

    con = get_conn()
    # debug util: vezi exact DB-ul și tabelele (poți comenta după ce e ok)
    # print("DB:", DB_PATH)
    # print("Tabele:", [r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")])

    user = con.execute("""
        SELECT id, username, email, parola, rol, grupe, copii
        FROM utilizatori
        WHERE username = ? OR email = ?
        LIMIT 1
    """, (username_or_email, username_or_email)).fetchone()

    if not user:
        return jsonify({"status": "error", "message": "Utilizator sau parolă incorecte"}), 401

    stored = user["parola"]
    if isinstance(stored, (bytes, bytearray)):
        stored = stored.decode("utf-8", "ignore")
    if not isinstance(stored, str):
        stored = str(stored)

    # 1) verificare normală (hash pbkdf2)
    ok = False
    try:
        ok = check_password(stored, password)   # True dacă e hash werkzeug valid
    except Exception:
        ok = False

    # 2) fallback: dacă era „plain” în DB (moștenit vechi)
    if not ok and stored and not stored.startswith("pbkdf2:"):
        ok = (stored == password)

    if not ok:
        return jsonify({"status": "error", "message": "Utilizator sau parolă incorecte"}), 401

    # Migrare la hash pbkdf2 dacă încă nu e
    if not stored.startswith("pbkdf2:"):
        new_hash = hash_password(password)
        con.execute("UPDATE utilizatori SET parola = ? WHERE id = ?", (new_hash, user["id"]))
        con.commit()

    return jsonify({
        "status": "success",
        "user": user["username"],
        "email": user["email"],
        "rol": user["rol"],
        "grupe": user["grupe"]
    }), 200
