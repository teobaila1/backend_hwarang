import jwt
import datetime
import os
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..passwords.security import hash_password, check_password  # wrappers peste werkzeug

# ATENȚIE: Această cheie trebuie să fie aceeași cu cea din 'decorators.py'
# În producție, folosește un fișier .env pentru a o ascunde.
SECRET_KEY = os.environ.get("SECRET_KEY", "cheie_super_secreta_hwarang_2026")

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

                # ── GENERARE TOKEN JWT (NOU) ─────────────────────────────────────────
                # Creăm un "pașaport" digital care expiră în 24 de ore
                token_payload = {
                    "id": user["id"],
                    "username": user["username"],
                    "rol": (user["rol"] or "").lower(),
                    "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
                }

                token = jwt.encode(token_payload, SECRET_KEY, algorithm="HS256")
                # ─────────────────────────────────────────────────────────────────────

        # Răspuns de succes care include TOKEN-ul
        return jsonify({
            "status": "success",
            "token": token,  # <--- Token-ul generat
            "user": user["username"],
            "email": user["email"],
            "rol": user["rol"],
            "grupe": user["grupe"],
        }), 200

    except Exception as e:
        # pentru debug poți loga `e` în server
        print(f"Eroare login: {e}")
        return jsonify({
            "status": "error",
            "message": "Eroare internă la autentificare."
        }), 500