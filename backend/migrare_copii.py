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

    # 1. DEBUG: Vedem mai întâi ce useri au date în coloana copii, indiferent de rol
    # Căutăm orice rând unde coloana copii are mai mult de 2 caractere (adică nu e "[]" sau gol)
    cur.execute("""
        SELECT id, username, rol, copii 
        FROM utilizatori 
        WHERE copii IS NOT NULL AND LENGTH(CAST(copii AS TEXT)) > 2
    """)
    candidates = cur.fetchall()

    debug_info = []
    count = 0
    errors = 0

    if not candidates:
        return jsonify({
            "status": "warning",
            "message": "Nu am găsit niciun utilizator cu date în coloana veche 'copii'.",
            "debug_query_result": "Empty"
        })

    for p in candidates:
        pid = p['id']
        username = p['username']
        raw_json = p['copii']
        rol = p['rol']

        debug_info.append(f"Gasit user: {username} ({rol}) | Data: {raw_json[:50]}...")

        try:
            # Parsare JSON
            if isinstance(raw_json, str):
                children_list = json.loads(raw_json)
            else:
                children_list = raw_json

            if not isinstance(children_list, list):
                continue

            for child in children_list:
                if not isinstance(child, dict): continue

                nume = child.get('nume')
                grupa = child.get('grupa')
                gen = child.get('gen')
                varsta = child.get('varsta')

                if not nume: continue

                # Verificăm duplicate în tabelul nou
                cur.execute("SELECT 1 FROM copii WHERE id_parinte = %s AND nume = %s", (pid, nume))
                if cur.fetchone():
                    # Deja migrat
                    continue

                # Calcul Data Nașterii
                dob = None
                if varsta and str(varsta).isdigit():
                    an_curent = datetime.datetime.now().year
                    dob = f"{an_curent - int(varsta)}-01-01"

                # INSERT COPII
                new_id = uuid.uuid4().hex
                cur.execute("""
                    INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                """, (new_id, pid, nume, gen, grupa, dob))

                # INSERT GRUPE
                if grupa:
                    g_norm = grupa.strip()
                    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
                    g_row = cur.fetchone()
                    gid = None
                    if g_row:
                        gid = g_row['id']
                    else:
                        cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
                        gid = cur.fetchone()['id']

                    cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                (gid, new_id))

                count += 1

        except Exception as e:
            errors += 1
            debug_info.append(f"Eroare la {username}: {str(e)}")
            continue

    con.commit()

    return jsonify({
        "status": "success",
        "mesaj": f"Migrare finalizata. Am mutat {count} copii.",
        "detalii_utilizatori_gasiti": debug_info
    })