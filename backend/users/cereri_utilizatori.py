# backend/users/cereri_utilizatori.py
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..auth.inregistrare import trimite_email_acceptare, trimite_email_respingere
# Atenție: verifică dacă importul de mai sus e corect în structura ta.
# Uneori e '..auth.inregistrare' sau '..accounts.inregistrare' în funcție de cum ai organizat folderele.
# Dacă primești eroare de import, lasă importul cum era la tine în fișierul original.

cereri_utilizatori_bp = Blueprint("cereri_utilizatori", __name__)


# --- util: asigură existența coloanei (PostgreSQL) ----------------------------
def _ensure_column(con, table: str, column: str, sql_type: str = "TEXT"):
    """
    Pentru PostgreSQL: verifică dacă o coloană există în information_schema.
    Dacă nu există, dă un ALTER TABLE ADD COLUMN.
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

        # Ne asigurăm că există coloanele necesare
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")
        _ensure_column(con, "cereri_utilizatori", "data_nasterii", "DATE")

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

        # Selectăm și data_nasterii pentru afișaj
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
                d_nastere = r.get("data_nasterii") # luăm data nașterii
                afisaj = r["afisaj"]
            else:
                # ajustăm unpacking-ul dacă r e tuplu (atenție la ordinea din SELECT)
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
def accepta_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        # Asigurăm coloanele și în tabela finală
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "nume_complet")
        _ensure_column(con, "utilizatori", "data_nasterii", "DATE")

        # 1. Luăm datele din cerere (INCLUSIV data_nasterii)
        cur.execute(
            """
            SELECT id, username, email, parola, tip, copii, grupe, nume_complet, data_nasterii
            FROM cereri_utilizatori
            WHERE id = %s
            """,
            (cerere_id,),
        )
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        if isinstance(row, dict):
            username = row["username"]
            email = row["email"]
            parola = row["parola"]
            tip = row["tip"]
            copii = row["copii"]
            grupe = row["grupe"]
            nume_complet = row["nume_complet"]
            data_nasterii = row.get("data_nasterii") # <--- Aici preluăm data
        else:
            _, username, email, parola, tip, copii, grupe, nume_complet, data_nasterii = row

        # Verificăm duplicate
        cur.execute(
            "SELECT 1 FROM utilizatori WHERE username = %s OR email = %s LIMIT 1",
            (username, email),
        )
        exists = cur.fetchone()
        if exists:
            return jsonify(
                {"error": "Există deja un utilizator cu acest username/email"}
            ), 409

        # 2. Inserăm în utilizatori (INCLUSIV data_nasterii)
        cur.execute(
            """
            INSERT INTO utilizatori (username, parola, rol, email, grupe, copii, nume_complet, data_nasterii)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                username,
                parola,
                tip,
                email,
                grupe,
                copii,
                (nume_complet or username),
                data_nasterii # <--- Aici o salvăm în tabelul final
            ),
        )

        # Ștergem cererea
        cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        con.commit()

        # Trimitem email
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
            return jsonify({"status": "success"}), 200

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