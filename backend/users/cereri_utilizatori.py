import json
import uuid
import re
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..accounts.inregistrare import trimite_email_acceptare, trimite_email_respingere
from ..accounts.decorators import token_required, admin_required

cereri_utilizatori_bp = Blueprint("cereri_utilizatori", __name__)


def _ensure_column(con, table: str, column: str, sql_type: str = "TEXT"):
    cur = con.cursor()
    # Verificare simplă dacă există coloana
    try:
        cur.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except:
        con.rollback()
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
        con.commit()


def _normalize_name(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    gn = _normalize_name(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (gn,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (gn,))
    return cur.fetchone()['id']


@cereri_utilizatori_bp.get("/api/cereri")
@token_required
@admin_required
def get_cereri():
    try:
        con = get_conn()
        cur = con.cursor()

        # Ne asigurăm că există coloanele necesare
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "cereri_utilizatori", "data_nasterii", "DATE")

        cur.execute("""
            SELECT id, username, email, tip, varsta, data_nasterii, 
                   COALESCE(nume_complet, username) AS afisaj 
            FROM cereri_utilizatori 
            ORDER BY id DESC
        """)
        cereri = cur.fetchall()

        lista = []
        for r in cereri:
            lista.append({
                "id": r["id"],
                "username": r["username"],
                "email": r["email"],
                "tip": r["tip"],
                "varsta": r["varsta"],
                "data_nasterii": str(r["data_nasterii"]) if r["data_nasterii"] else None,
                "nume_complet": r["afisaj"],
            })

        return jsonify(lista), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.post("/api/cereri/accepta/<int:cerere_id>")
@token_required
@admin_required
def accepta_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()

        # 1. Luăm datele cererii
        cur.execute("SELECT * FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        username = row["username"]
        email = row["email"]
        parola = row["parola"]
        rol = row["tip"]  # 'tip' din cerere devine 'rol'
        copii_json = row["copii"]  # JSON string
        grupe_str = row["grupe"]
        nume_complet = row.get("nume_complet") or username
        data_nasterii = row.get("data_nasterii")

        # 2. Verificăm duplicate
        cur.execute("SELECT 1 FROM utilizatori WHERE username = %s OR email = %s LIMIT 1", (username, email))
        if cur.fetchone():
            return jsonify({"error": "Există deja un utilizator cu acest username/email"}), 409

        # 3. Inserăm în UTILIZATORI
        cur.execute("""
            INSERT INTO utilizatori (username, parola, rol, email, grupe, copii, nume_complet, data_nasterii, is_placeholder)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
            RETURNING id
        """, (username, parola, rol, email, grupe_str, copii_json, nume_complet, data_nasterii))

        new_user_id = cur.fetchone()['id']

        # 4. Inserăm în ROLURI (Critic!)
        cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, %s)", (new_user_id, rol))

        # 5. Procesăm COPIII (Migrare din JSON în tabelul SQL)
        if rol == 'Parinte' and copii_json:
            try:
                copii_list = json.loads(copii_json)
                if isinstance(copii_list, list):
                    for c in copii_list:
                        c_nume = c.get("nume")
                        c_grupa = c.get("grupa")
                        c_gen = c.get("gen")

                        if c_nume:
                            new_child_id = uuid.uuid4().hex
                            # Insert în COPII
                            cur.execute("""
                                INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, added_by_trainer)
                                VALUES (%s, %s, %s, %s, %s, FALSE)
                            """, (new_child_id, new_user_id, c_nume, c_gen, c_grupa))

                            # Insert în SPORTIVI_PE_GRUPE
                            if c_grupa:
                                gid = _get_or_create_group_id(cur, c_grupa)
                                if gid:
                                    cur.execute(
                                        "INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                        (gid, new_child_id))
            except Exception as ex:
                print(f"[WARN] Eroare la migrarea copiilor din cerere: {ex}")

        # 6. Procesăm ANTRENOR/SPORTIV (Grupe)
        if rol == 'Antrenor' and grupe_str:
            gr_list = [g.strip() for g in grupe_str.split(',') if g.strip()]
            for g in gr_list:
                gid = _get_or_create_group_id(cur, g)
                cur.execute("UPDATE grupe SET id_antrenor = %s WHERE id = %s", (new_user_id, gid))

        # 7. Ștergem cererea
        cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        con.commit()

        try:
            trimite_email_acceptare(email, username)
        except:
            pass

        return jsonify({"status": "success"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"error": str(e)}), 500


@cereri_utilizatori_bp.delete("/api/cereri/respingere/<int:cerere_id>")
@token_required
@admin_required
def respinge_cerere(cerere_id: int):
    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute("SELECT username, email FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        row = cur.fetchone()

        if row:
            email = row["email"]
            username = row["username"]
            cur.execute("DELETE FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
            con.commit()
            try:
                trimite_email_respingere(email, username)
            except:
                pass

        return jsonify({"status": "success"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500