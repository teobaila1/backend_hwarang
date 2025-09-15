# backend/users/cereri_utilizatori.py
from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH
from ..accounts.inregistrare import trimite_email_acceptare, trimite_email_respingere

cereri_utilizatori_bp = Blueprint("cereri_utilizatori", __name__)

# --- util: asigură existența coloanei (migrare non-destructivă) ----------------
def _ensure_column(con, table: str, column: str, sql_type: str = "TEXT"):
    cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        con.commit()
# -------------------------------------------------------------------------------


@cereri_utilizatori_bp.get("/api/cereri")
def get_cereri():
    username = (request.args.get("username") or "").strip()
    if not username:
        return jsonify({"error": "Lipsește username-ul"}), 401

    try:
        con = get_conn()

        # asigurăm coloanele noi (rulă doar dacă lipsesc)
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")

        # verifică rolul de admin
        row = con.execute(
            "SELECT rol FROM utilizatori WHERE username = ? LIMIT 1",
            (username,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Utilizator inexistent"}), 404
        if (row["rol"] or "").lower() != "admin":
            return jsonify({"error": "Acces interzis"}), 403

        # expunem și numele pentru afișaj (fallback pe username)
        cereri = con.execute("""
            SELECT id,
                   username,
                   email,
                   tip,
                   varsta,
                   COALESCE(nume_complet, username) AS afisaj
            FROM cereri_utilizatori
            ORDER BY id DESC
        """).fetchall()

        lista = [
            {
                "id": r["id"],
                "username": r["username"],
                "email": r["email"],
                "tip": r["tip"],
                "varsta": r["varsta"],
                "nume_complet": r["afisaj"],    # numele de afișat în listă
            }
            for r in cereri
        ]
        return jsonify(lista), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.post("/api/cereri/accepta/<int:cerere_id>")
def accepta_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        # asigurăm coloanele noi (rulă doar dacă lipsesc)
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")

        row = cur.execute("""
            SELECT id, username, email, parola, tip, copii, grupe, nume_complet
            FROM cereri_utilizatori
            WHERE id = ?
        """, (cerere_id,)).fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        _, username, email, parola, tip, copii, grupe, nume_complet = (
            row["id"], row["username"], row["email"], row["parola"],
            row["tip"], row["copii"], row["grupe"], row["nume_complet"]
        )

        # verifică duplicate în utilizatori
        exists = cur.execute(
            "SELECT 1 FROM utilizatori WHERE username = ? OR email = ? LIMIT 1",
            (username, email)
        ).fetchone()
        if exists:
            return jsonify({"error": "Există deja un utilizator cu acest username/email"}), 409

        # inserăm în utilizatori și numele complet (fallback pe username)
        cur.execute("""
            INSERT INTO utilizatori (username, parola, rol, email, grupe, copii, nume_complet)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, parola, tip, email, grupe, copii, (nume_complet or username)))

        # ștergem cererea
        cur.execute("DELETE FROM cereri_utilizatori WHERE id = ?", (cerere_id,))
        con.commit()

        # e-mail după commit (non-blocking)
        try:
            trimite_email_acceptare(email, username)
        except Exception as e:
            print("[WARN] Email acceptare eșuat:", e)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.delete("/api/cereri/respingere/<int:cerere_id>")
def respinge_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        row = cur.execute(
            "SELECT username, email FROM cereri_utilizatori WHERE id = ?",
            (cerere_id,)
        ).fetchone()

        if not row:
            return jsonify({"status": "success"}), 200  # deja nu există

        username, email = row["username"], row["email"]

        cur.execute("DELETE FROM cereri_utilizatori WHERE id = ?", (cerere_id,))
        con.commit()

        try:
            trimite_email_respingere(email, username)
        except Exception as e:
            print("[WARN] Email respingere eșuat:", e)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
