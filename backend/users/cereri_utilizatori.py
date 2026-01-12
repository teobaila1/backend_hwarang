# backend/users/cereri_utilizatori.py
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..accounts.inregistrare import trimite_email_acceptare, trimite_email_respingere
# Importăm decoratorii
from ..accounts.decorators import token_required, admin_required

cereri_utilizatori_bp = Blueprint("cereri_utilizatori", __name__)

# ... (păstrează funcția _ensure_column neschimbată) ...
def _ensure_column(con, table: str, column: str, sql_type: str = "TEXT"):
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

@cereri_utilizatori_bp.get("/api/cereri")
@token_required
@admin_required  # <--- SECURIZAT
def get_cereri():
    # Nu mai verificăm manual username/rol, decoratorii fac asta
    try:
        con = get_conn()
        cur = con.cursor()

        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")
        _ensure_column(con, "cereri_utilizatori", "data_nasterii", "DATE")

        cur.execute(
            """
            SELECT id,
                   username,
                   email,
                   tip,
                   varsta,
                   data_nasterii,
                   COALESCE(nume_complet, username) AS afisaj
            FROM cereri_utilizatori
            ORDER BY id DESC
            """
        )
        cereri = cur.fetchall()

        lista = []
        for r in cereri:
            if isinstance(r, dict):
                rid = r["id"]
                user = r["username"]
                email = r["email"]
                tip = r["tip"]
                varsta = r["varsta"]
                d_nastere = r.get("data_nasterii")
                afisaj = r["afisaj"]
            else:
                rid, user, email, tip, varsta, d_nastere, afisaj = r

            lista.append(
                {
                    "id": rid,
                    "username": user,
                    "email": email,
                    "tip": tip,
                    "varsta": varsta,
                    "data_nasterii": str(d_nastere) if d_nastere else None,
                    "nume_complet": afisaj,
                }
            )

        return jsonify(lista), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.post("/api/cereri/accepta/<int:cerere_id>")
@token_required
@admin_required  # <--- SECURIZAT
def accepta_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "data_nasterii", "DATE")

        cur.execute(
            "SELECT * FROM cereri_utilizatori WHERE id = %s",
            (cerere_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        # Maparea rândului la variabile (depinde de driver, dict sau tuple)
        # Simplificăm folosind direct numele coloanelor dacă e dict (Psycopg2 RealDictCursor)
        # sau accesând prin index dacă e tuplu (dar aici presupunem că ai configurat dict cursor sau accesăm sigur)
        # Pentru siguranță maximă, extragem datele esențiale:
        username = row["username"]
        email = row["email"]
        parola = row["parola"]
        tip = row["tip"] # devine rol
        copii = row["copii"]
        grupe = row["grupe"]
        nume_complet = row["nume_complet"]
        data_nasterii = row.get("data_nasterii")

        # Verificăm duplicate
        cur.execute(
            "SELECT 1 FROM utilizatori WHERE username = %s OR email = %s LIMIT 1",
            (username, email),
        )
        if cur.fetchone():
            return jsonify({"error": "Există deja un utilizator cu acest username/email"}), 409

        # Inserăm
        cur.execute(
            """
            INSERT INTO utilizatori (username, parola, rol, email, grupe, copii, nume_complet, data_nasterii)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (username, parola, tip, email, grupe, copii, (nume_complet or username), data_nasterii),
        )

        cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        con.commit()

        try:
            trimite_email_acceptare(email, username)
        except Exception as e:
            print("[WARN] Email acceptare eșuat:", e)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.delete("/api/cereri/respingere/<int:cerere_id>")
@token_required
@admin_required  # <--- SECURIZAT
def respinge_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        cur.execute("SELECT username, email FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({"status": "success"}), 200

        username = row["username"]
        email = row["email"]

        cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        con.commit()

        try:
            trimite_email_respingere(email, username)
        except Exception as e:
            print("[WARN] Email respingere eșuat:", e)

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500