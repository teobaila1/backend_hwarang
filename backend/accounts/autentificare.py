# backend/accounts/autentificare.py
from flask import Blueprint, request, jsonify, session   # ✅ adaugă session
from ..config import get_conn, DB_PATH
from ..passwords.security import hash_password, check_password

autentificare_bp = Blueprint("autentificare", __name__)

@autentificare_bp.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username_or_email = data.get("username") or data.get("email")
    password = data.get("password") or data.get("parola")

    if not username_or_email or not password:
        return jsonify({"status": "error", "message": "Date incomplete"}), 400

    con = get_conn()
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

    ok = False
    try:
        ok = check_password(stored, password)
    except Exception:
        ok = False
    if not ok and stored and not stored.startswith("pbkdf2:"):
        ok = (stored == password)
    if not ok:
        return jsonify({"status": "error", "message": "Utilizator sau parolă incorecte"}), 401

    # Migrare la hash pbkdf2 dacă încă nu e
    if not stored.startswith("pbkdf2:"):
        new_hash = hash_password(password)
        con.execute("UPDATE utilizatori SET parola = ? WHERE id = ?", (new_hash, user["id"]))
        con.commit()

    # ✅ Salvează identitatea minimă în sesiune
    session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        # dacă ai 1 rol string, îl transformăm într-o listă:
        "roles": [r.strip() for r in (user["rol"] or "").split(",") if r.strip()] or (
            [user["rol"]] if user["rol"] else []),
        "grupe": user["grupe"],
    }
    return jsonify({
        "status": "success",
        "user": user["username"],
        "email": user["email"],
        "rol": user["rol"],
        "grupe": user["grupe"]
    }), 200
