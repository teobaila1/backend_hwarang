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

    # Logică normalizare rapidă (ex: "1" -> "Grupa 1")
    if gn.isdigit():
        gn = f"Grupa {gn}"
    elif gn.lower().startswith("gr") and any(c.isdigit() for c in gn):
        nums = re.findall(r'\d+', gn)
        if nums: gn = f"Grupa {nums[0]}"

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
                   COALESCE(nume_complet, username) AS afisaj, grupe, copii 
            FROM cereri_utilizatori 
            ORDER BY id DESC
        """)
        cereri = cur.fetchall()

        lista = []
        for r in cereri:
            # Parsăm copiii pentru afișare corectă în frontend
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
        cur = con.cursor()

        # 1. Luăm datele cererii
        cur.execute("SELECT * FROM cereri_utilizatori WHERE id = %s", (cerere_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({"error": "Cerere inexistentă"}), 404

        username = row["username"]
        email = row["email"]
        parola = row["parola"]  # Hash-ul gata făcut din inregistrare.py
        rol = row["tip"]  # 'tip' din cerere devine 'rol'
        copii_json = row["copii"]  # JSON string
        grupe_str = row["grupe"]
        nume_complet = row.get("nume_complet") or username
        data_nasterii = row.get("data_nasterii")

        # 2. Verificăm duplicate
        cur.execute("SELECT 1 FROM utilizatori WHERE username = %s OR email = %s LIMIT 1", (username, email))
        if cur.fetchone():
            return jsonify({"error": "Există deja un utilizator cu acest username/email"}), 409

        # 3. Inserăm în UTILIZATORI (Aici intră în tabela principală)
        # Atenție: folosim password_hash în DB, dar 'parola' din row deja e hashuită în inregistrare.py
        cur.execute("""
            INSERT INTO utilizatori (username, password_hash, rol, email, grupe, copii, nume_complet, data_nasterii)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (username, parola, rol, email, grupe_str, copii_json, nume_complet, data_nasterii))

        new_user_id = cur.fetchone()['id']

        # 4. (Opțional) Inserăm în ROLURI dacă folosești acea tabelă, dacă nu, e ok să fie comentat sau șters
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
                        c_grupa = c.get("grupa")
                        c_gen = c.get("gen")

                        # Calculăm data nașterii copilului din vârstă (aproximativ)
                        c_varsta = c.get("varsta")
                        dn_copil = None
                        if c_varsta and str(c_varsta).isdigit():
                            an_nastere = 2024 - int(c_varsta)  # Aproximare
                            dn_copil = f"{an_nastere}-01-01"

                        if c_nume:
                            new_child_id = uuid.uuid4().hex
                            # Insert în COPII
                            cur.execute("""
                                INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
                                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                            """, (new_child_id, new_user_id, c_nume, c_gen, c_grupa, dn_copil))

                            # Insert în SPORTIVI_PE_GRUPE (Copil)
                            if c_grupa:
                                gid = _get_or_create_group_id(cur, c_grupa)
                                if gid:
                                    cur.execute(
                                        "INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                        (gid, new_child_id))
            except Exception as ex:
                print(f"[WARN] Eroare la migrarea copiilor din cerere: {ex}")

        # 6. Procesăm SPORTIV (Adult) -> Legăm de grupă
        # --- AICI ESTE FIXUL CERUT DE TINE ---
        if rol == 'Sportiv' and grupe_str:
            gr_list = [g.strip() for g in grupe_str.split(',') if g.strip()]
            for g in gr_list:
                gid = _get_or_create_group_id(cur, g)
                if gid:
                    try:
                        # Îl legăm ca adult (id_sportiv_user)
                        cur.execute("""
                            INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_user) 
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (gid, new_user_id))
                        print(f"[ACCEPT] Sportiv {username} legat de {g} (ID: {gid})")
                    except Exception as e:
                        print(f"[ERROR] Nu am putut lega sportivul de grupă: {e}")

        # 7. Procesăm ANTRENOR
        if rol == 'Antrenor' and grupe_str:
            gr_list = [g.strip() for g in grupe_str.split(',') if g.strip()]
            for g in gr_list:
                gid = _get_or_create_group_id(cur, g)
                # Dacă ai tabela nouă antrenori_pe_grupe
                try:
                    cur.execute(
                        "INSERT INTO antrenori_pe_grupe (id_grupa, id_antrenor) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (gid, new_user_id))
                except:
                    # Fallback pe vechea coloană
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