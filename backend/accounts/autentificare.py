# backend/accounts/autentificare.py
from flask import Blueprint, request, jsonify, session   # ✅ folosim session
from flask_cors import cross_origin                      # ✅ CORS per-rută cu credențiale
from ..config import get_conn, DB_PATH
from ..passwords.security import hash_password, check_password

autentificare_bp = Blueprint("autentificare", __name__)

# ✅ permite cookie de sesiune cross-site (Netlify → Render)
#    * origins: pune aici exact domeniile tale de producție
_ALLOWED_ORIGINS = [
    "https://hwarangsibiu.netlify.app",
    "https://acshwarangacademysibiu.netlify.app",
    "http://localhost:5173",      # util în dev, elimină în producție dacă vrei
    "http://127.0.0.1:5173",
]

@autentificare_bp.post("/api/login")
@cross_origin(supports_credentials=True, origins=_ALLOWED_ORIGINS)
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

    # ✅ Migrare la hash pbkdf2 dacă încă nu e
    if not stored.startswith("pbkdf2:"):
        new_hash = hash_password(password)
        con.execute("UPDATE utilizatori SET parola = ? WHERE id = ?", (new_hash, user["id"]))
        con.commit()

    # ✅ Setează sesiunea (browserul primește Set-Cookie pentru sesiunea Flask)
    #    Notă: cookie-ul va fi acceptat cross-site doar dacă backend-ul are:
    #    SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_SECURE=True (în producție/HTTPS)
    session.permanent = True
    session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "email": user["email"],
        # transformă string-ul de roluri într-o listă
        "roles": [r.strip() for r in (user["rol"] or "").split(",") if r.strip()] or (
            [user["rol"]] if user["rol"] else []
        ),
        "grupe": user["grupe"],
    }

    return jsonify({
        "status": "success",
        "user": user["username"],
        "email": user["email"],
        "rol": user["rol"],
        "grupe": user["grupe"]
    }), 200
