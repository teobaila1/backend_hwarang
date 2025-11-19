from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..passwords.security import hash_password, check_password  # wrappers peste werkzeug

autentificare_bp = Blueprint("autentificare", __name__)


@autentificare_bp.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}

    username_or_email = (data.get("username") or data.get("email") or "").strip()
    password = (data.get("password") or data.get("parola") or "").strip()

    if not username_or_email or not password:
        return jsonify({"status": "error", "message": "Date incomplete."}), 400

    try:
        with get_conn() as con:
            with con.cursor() as cur:
                # Căutăm utilizatorul după username SAU email (case-insensitive)
                cur.execute(
                    """
                    SELECT
                        id,
                        username,
                        email,
                        parola,
                        rol,
                        grupe
                    FROM utilizatori
                    WHERE LOWER(username) = LOWER(%s)
                       OR LOWER(email) = LOWER(%s)
                    LIMIT 1
                    """,
                    (username_or_email, username_or_email),
                )
                user = cur.fetchone()

                if not user:
                    return jsonify({
                        "status": "error",
                        "message": "Utilizator sau parolă incorecte."
                    }), 401

                stored_password = (user.get("parola") or "").strip()

                # ── Verificare parolă ────────────────────────────────────────────────
                is_valid = False

                if stored_password.startswith("pbkdf2:"):
                    # parola este deja hash-uită -> verificăm cu check_password
                    is_valid = check_password(stored_password, password)
                else:
                    # parola veche, probabil în clar -> comparăm direct
                    if stored_password == password:
                        is_valid = True
                    else:
                        is_valid = False

                if not is_valid:
                    return jsonify({
                        "status": "error",
                        "message": "Utilizator sau parolă incorecte."
                    }), 401

                # ── Migrare automată la hash pbkdf2 dacă parola nu e încă hash-uită ─
                if stored_password and not stored_password.startswith("pbkdf2:"):
                    new_hash = hash_password(password)
                    cur.execute(
                        "UPDATE utilizatori SET parola = %s WHERE id = %s",
                        (new_hash, user["id"]),
                    )
                    con.commit()

        # răspuns de succes
        return jsonify({
            "status": "success",
            "user": user["username"],
            "email": user["email"],
            "rol": user["rol"],
            "grupe": user["grupe"],
        }), 200

    except Exception as e:
        # pentru debug poți loga `e` în server
        return jsonify({
            "status": "error",
            "message": "Eroare internă la autentificare."
        }), 500
