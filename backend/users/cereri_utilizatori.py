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
    try:
        cur.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except:
        con.rollback()
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}")
            con.commit()
        except Exception as e:
            print(f"[WARN] Nu am putut adăuga coloana {column}: {e}")


def _normalize_name(s):
    return re.sub(r"\s+", " ", (s or "").strip())


# --- FUNCȚIE NOUĂ DE CURĂȚARE GRUPĂ ---
def _normalize_group_name(g):
    if not g: return ""
    g = str(g).strip()

    # "1" -> "Grupa 1"
    if g.isdigit():
        return f"Grupa {g}"

    # "gr 1", "Gr.1" -> "Grupa 1"
    if g.lower().startswith("gr") and any(c.isdigit() for c in g):
        nums = re.findall(r'\d+', g)
        if nums: return f"Grupa {nums[0]}"

    # Altfel returnăm textul curat (ex: "Baby Hwarang")
    return _normalize_name(g)


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    # Folosim funcția de normalizare aici
    gn = _normalize_group_name(group_name)

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

        # Asigurăm coloanele
        _ensure_column(con, "cereri_utilizatori", "nume_complet")
        _ensure_column(con, "cereri_utilizatori", "data_nasterii", "DATE")
        _ensure_column(con, "cereri_utilizatori", "copii", "TEXT")
        _ensure_column(con, "cereri_utilizatori", "grupe", "TEXT")

        cur = con.cursor()
        cur.execute("""
            SELECT id, username, email, tip, varsta, data_nasterii, 
                   COALESCE(nume_complet, username) AS afisaj, grupe, copii 
            FROM cereri_utilizatori 
            ORDER BY id DESC
        """)
        cereri = cur.fetchall()

        lista = []
        for r in cereri:
            copii_parsed = []
            if r['copii']:
                try:
                    copii_parsed = json.loads(r['copii'])
                except:
                    pass

            lista.append({
                "id": r["id"],
                "username": r["username"],
                "email": r["email"],
                "tip": r["tip"],
                "varsta": r["varsta"],
                "data_nasterii": str(r["data_nasterii"]) if r["data_nasterii"] else None,
                "nume_complet": r["afisaj"],
                "grupe": r["grupe"],
                "copii": copii_parsed
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

        # Asigurăm coloanele în tabela finală
        _ensure_column(con, "utilizatori", "nume_complet", "TEXT")
        _ensure_column(con, "utilizatori", "data_nasterii", "DATE")
        _ensure_column(con, "utilizatori", "grupe", "TEXT")
        _ensure_column(con, "utilizatori", "copii", "TEXT")

        cur = con.cursor()

        # 1. Luăm datele cererii
        cur.execute("SELECT * FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        username = row["username"]
        email = row["email"]
        parola = row["parola"]
        rol = row["tip"]
        copii_json = row["copii"]
        grupe_str = row["grupe"]
        nume_complet = row.get("nume_complet") or username
        data_nasterii = row.get("data_nasterii")

        # 2. Verificăm duplicate
        cur.execute("SELECT 1 FROM utilizatori WHERE username = %s OR email = %s LIMIT 1", (username, email))
        if cur.fetchone():
            return jsonify({"error": "Există deja un utilizator cu acest username/email"}), 409

        # 3. Inserăm în UTILIZATORI
        cur.execute("""
            INSERT INTO utilizatori (username, parola, rol, email, grupe, copii, nume_complet, data_nasterii)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (username, parola, rol, email, grupe_str, copii_json, nume_complet, data_nasterii))

        new_user_id = cur.fetchone()['id']

        # 4. Inserăm în ROLURI
        try:
            cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, %s)", (new_user_id, rol))
        except:
            pass

            # 5. Procesăm PĂRINTE (Copii)
        if rol == 'Parinte' and copii_json:
            try:
                copii_list = json.loads(copii_json)
                if isinstance(copii_list, list):
                    for c in copii_list:
                        c_nume = c.get("nume")
                        c_grupa_raw = c.get("grupa")  # Ce a scris părintele (ex: "1")
                        c_gen = c.get("gen")
                        c_varsta = c.get("varsta")

                        # A. Normalizare Nume Grupă ("1" -> "Grupa 1")
                        c_grupa_final = _normalize_group_name(c_grupa_raw)

                        # B. Auto-completare Nume Familie Copil
                        if c_nume and " " not in c_nume.strip():
                            if nume_complet:
                                parts_parinte = _normalize_name(nume_complet).split()
                                if len(parts_parinte) > 0:
                                    nume_fam = parts_parinte[0]
                                    c_nume = f"{nume_fam} {c_nume}"
                                    print(f"[AUTO-NAME] Completat: {c_nume}")

                        # C. Calcul Data Nașterii
                        dn_copil = None
                        if c_varsta and str(c_varsta).isdigit():
                            an_nastere = 2024 - int(c_varsta)
                            dn_copil = f"{an_nastere}-01-01"

                        # D. Inserare
                        if c_nume:
                            new_child_id = uuid.uuid4().hex
                            # Inserăm în COPII folosind numele de grupă FRUMOS (c_grupa_final)
                            cur.execute("""
                                INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
                                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                            """, (new_child_id, new_user_id, c_nume, c_gen, c_grupa_final, dn_copil))

                            # Facem legătura
                            if c_grupa_final:
                                gid = _get_or_create_group_id(cur, c_grupa_final)
                                if gid:
                                    cur.execute(
                                        "INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                        (gid, new_child_id))
            except Exception as ex:
                print(f"[WARN] Eroare la migrarea copiilor: {ex}")

        # 6. Procesăm SPORTIV (Adult)
        if rol == 'Sportiv' and grupe_str:
            gr_list = [g.strip() for g in grupe_str.split(',') if g.strip()]
            for g_raw in gr_list:
                # Normalizăm și aici, just in case
                g_final = _normalize_group_name(g_raw)

                gid = _get_or_create_group_id(cur, g_final)
                if gid:
                    try:
                        cur.execute("""
                            INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_user) 
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (gid, new_user_id))
                    except Exception as e:
                        print(f"[ERROR] Nu am putut lega sportivul de grupă: {e}")

        # 7. Procesăm ANTRENOR
        if rol == 'Antrenor' and grupe_str:
            gr_list = [g.strip() for g in grupe_str.split(',') if g.strip()]
            for g_raw in gr_list:
                g_final = _normalize_group_name(g_raw)
                gid = _get_or_create_group_id(cur, g_final)
                try:
                    cur.execute(
                        "INSERT INTO antrenori_pe_grupe (id_grupa, id_antrenor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (gid, new_user_id))
                except:
                    cur.execute("UPDATE grupe SET id_antrenor = %s WHERE id = %s", (new_user_id, gid))

        # 8. Ștergem cererea
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