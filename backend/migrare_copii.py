import json
import uuid
import datetime
from flask import Blueprint, jsonify
from backend.config import get_conn

# Nu mai importăm decoratorii pentru că îi scoatem temporar
# from backend.accounts.decorators import admin_required, token_required

migrare_bp = Blueprint('migrare', __name__)


# --- NOTĂ: Am scos securitatea (@token_required) ca să poți rula scriptul direct din browser ---
@migrare_bp.get('/api/admin/migrare_fortata')
def run_migration():
    con = get_conn()
    cur = con.cursor()

    # 1. Luăm toți părinții care au date în coloana veche 'copii'
    try:
        cur.execute("SELECT id, copii FROM utilizatori WHERE rol = 'Parinte' AND copii IS NOT NULL")
        parinti = cur.fetchall()
    except Exception as e:
        return jsonify({"status": "error", "message": f"Eroare SQL initiala: {str(e)}"}), 500

    count = 0
    errors = 0

    for p in parinti:
        pid = p['id']
        raw_json = p['copii']

        try:
            if not raw_json: continue
            # Uneori JSON-ul e stocat ciudat, încercăm să-l reparăm basic
            if isinstance(raw_json, str):
                children_list = json.loads(raw_json)
            else:
                # Dacă e deja dict/list (unele drivere SQL fac conversia automat)
                children_list = raw_json

            if not isinstance(children_list, list): continue

            for child in children_list:
                if not isinstance(child, dict): continue

                nume = child.get('nume')
                grupa = child.get('grupa')
                gen = child.get('gen')
                varsta = child.get('varsta')

                if not nume: continue

                # Verificăm dacă există deja în tabelul nou
                cur.execute("SELECT 1 FROM copii WHERE id_parinte = %s AND nume = %s", (pid, nume))
                if cur.fetchone(): continue

                # Calculăm data nașterii
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

                # INSERT GRUPE (Legătura pentru antrenor)
                if grupa:
                    g_norm = grupa.strip()
                    # Căutăm grupa sau o creăm
                    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
                    g_row = cur.fetchone()
                    gid = None
                    if g_row:
                        gid = g_row['id']
                    else:
                        cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
                        gid = cur.fetchone()['id']

                    # Legăm copilul de grupă
                    cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                (gid, new_id))

                count += 1

        except Exception as e:
            print(f"Eroare la parintele ID {pid}: {e}")
            errors += 1
            continue

    con.commit()
    return jsonify({
        "status": "success",
        "mesaj": f"EXECUTAT! Am mutat {count} copii. Erori intampinate: {errors}"
    })