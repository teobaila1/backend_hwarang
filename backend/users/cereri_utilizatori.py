# backend/users/cereri_utilizatori.py
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..accounts.inregistrare import trimite_email_acceptare, trimite_email_respingere

cereri_utilizatori_bp = Blueprint("cereri_utilizatori", __name__)


# --- util: asigură existența coloanei (PostgreSQL) ----------------------------
def _ensure_column(con, table: str, column: str, sql_type: str = "TEXT"):
    """
    Pentru PostgreSQL: verifică dacă o coloană există în information_schema.
    Dacă nu există, dă un ALTER TABLE ADD COLUMN.
    Rularea repetată e sigură: dacă există, nu face nimic.
    """
    cur = con.cursor()
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    exists = cur.fetchone()
    if not exists:
        cur.execute(
            f'ALTER TABLE {table} ADD COLUMN {column} {sql_type}'
        )
        con.commit()
# -----------------------------------------------------------------------------


@cereri_utilizatori_bp.get("/api/cereri")
def get_cereri():
    username = (request.args.get("username") or "").strip()
    if not username:
        return jsonify({"error": "Lipsește username-ul"}), 401

    try:
        con = get_conn()
        cur = con.cursor()

        # asigurăm coloanele noi (rulează doar dacă lipsesc)
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")

        # verifică rolul de admin
        cur.execute(
            "SELECT rol FROM utilizatori WHERE username = %s LIMIT 1",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Utilizator inexistent"}), 404

        rol = (row["rol"] if isinstance(row, dict) else row[0]) or ""
        if rol.lower() != "admin":
            return jsonify({"error": "Acces interzis"}), 403

        # expunem și numele pentru afișaj (fallback pe username)
        cur.execute(
            """
            SELECT id,
                   username,
                   email,
                   tip,
                   varsta,
                   COALESCE(nume_complet, username) AS afisaj
            FROM cereri_utilizatori
            ORDER BY id DESC
            """
        )
        cereri = cur.fetchall()

        lista = []
        for r in cereri:
            # suport atât pentru DictRow cât și pentru tuple, în caz că se schimbă cursor_factory
            if isinstance(r, dict):
                rid = r["id"]
                user = r["username"]
                email = r["email"]
                tip = r["tip"]
                varsta = r["varsta"]
                afisaj = r["afisaj"]
            else:
                rid, user, email, tip, varsta, afisaj = r

            lista.append(
                {
                    "id": rid,
                    "username": user,
                    "email": email,
                    "tip": tip,
                    "varsta": varsta,
                    "nume_complet": afisaj,  # numele de afișat în listă
                }
            )

        return jsonify(lista), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.post("/api/cereri/accepta/<int:cerere_id>")
def accepta_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        # asigurăm coloanele noi (rulează doar dacă lipsesc)
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")

        cur.execute(
            """
            SELECT id, username, email, parola, tip, copii, grupe, nume_complet
            FROM cereri_utilizatori
            WHERE id = %s
            """,
            (cerere_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        if isinstance(row, dict):
            _, username, email, parola, tip, copii, grupe, nume_complet = (
                row["id"],
                row["username"],
                row["email"],
                row["parola"],
                row["tip"],
                row["copii"],
                row["grupe"],
                row["nume_complet"],
            )
        else:
            _, username, email, parola, tip, copii, grupe, nume_complet = row

        # verifică duplicate în utilizatori
        cur.execute(
            "SELECT 1 FROM utilizatori WHERE username = %s OR email = %s LIMIT 1",
            (username, email),
        )
        exists = cur.fetchone()
        if exists:
            return jsonify(
                {"error": "Există deja un utilizator cu acest username/email"}
            ), 409

        # inserăm în utilizatori și numele complet (fallback pe username)
        cur.execute(
            """
            INSERT INTO utilizatori (username, parola, rol, email, grupe, copii, nume_complet)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (username, parola, tip, email, grupe, copii, (nume_complet or username)),
        )

        # ștergem cererea
        cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
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

        cur.execute(
            "SELECT username, email FROM cereri_utilizatori WHERE id = %s",
            (cerere_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"status": "success"}), 200  # deja nu există

        if isinstance(row, dict):
            username, email = row["username"], row["email"]
        else:
            username, email = row

        cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        con.commit()

        try:
            trimite_email_respingere(email, username)
        except Exception as e:
            print("[WARN] Email respingere eșuat:", e)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
