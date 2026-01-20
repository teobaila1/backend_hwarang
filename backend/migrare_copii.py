import json
import uuid
import datetime
from flask import Blueprint, jsonify
from backend.config import get_conn

migrare_bp = Blueprint('migrare', __name__)


@migrare_bp.get('/api/admin/migrare_fortata')
def run_migration():
    con = get_conn()
    cur = con.cursor()

    # 1. Căutăm utilizatorii cu date vechi
    cur.execute("""
        SELECT id, username, rol, copii 
        FROM utilizatori 
        WHERE copii IS NOT NULL AND LENGTH(CAST(copii AS TEXT)) > 2
    """)
    candidates = cur.fetchall()

    if not candidates:
        return jsonify({"status": "warning", "message": "Nu am găsit date vechi de migrat."})

    logs = []
    total_inserted = 0

    for p in candidates:
        pid = p['id']
        username = p['username']
        raw_json = p['copii']

        try:
            # Parsare JSON
            if isinstance(raw_json, str):
                children_list = json.loads(raw_json)
            else:
                children_list = raw_json

            if not isinstance(children_list, list) or not children_list:
                continue

            # --- PASUL CRITIC: Curățăm datele existente ale acestui părinte ---
            # Ștergem copiii din tabelul nou pentru a evita duplicatele și a forța re-scrierea
            cur.execute("DELETE FROM copii WHERE id_parinte = %s", (pid,))

            # Re-inserăm copiii curați
            children_added_for_user = 0

            for child in children_list:
                if not isinstance(child, dict): continue

                nume = child.get('nume')
                if not nume: continue

                grupa = child.get('grupa')
                gen = child.get('gen')
                varsta = child.get('varsta')

                # Calcul Data Nașterii
                dob = None
                if varsta and str(varsta).isdigit():
                    an_curent = datetime.datetime.now().year
                    dob = f"{an_curent - int(varsta)}-01-01"

                new_id = uuid.uuid4().hex

                # INSERT
                cur.execute("""
                    INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                """, (new_id, pid, nume, gen, grupa, dob))

                # REPARĂM ȘI GRUPELE
                if grupa:
                    g_norm = grupa.strip()
                    # Căutăm ID grupă
                    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
                    g_row = cur.fetchone()
                    gid = None
                    if g_row:
                        gid = g_row['id']
                    else:
                        cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
                        gid = cur.fetchone()['id']

                    # Ștergem asocieri vechi (dacă există orfane) și adăugăm
                    cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                (gid, new_id))

                children_added_for_user += 1
                total_inserted += 1

            logs.append(f"User {username}: Stersi vechi -> Adaugati {children_added_for_user} noi.")

        except Exception as e:
            logs.append(f"EROARE la {username}: {str(e)}")
            continue

    con.commit()

    return jsonify({
        "status": "success",
        "total_copii_rescrisi": total_inserted,
        "detalii": logs
    })