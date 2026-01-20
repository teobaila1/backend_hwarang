import json
import uuid
import datetime
from flask import Blueprint, jsonify
from backend.config import get_conn
from backend.accounts.decorators import admin_required, token_required

migrare_bp = Blueprint('migrare', __name__)


@migrare_bp.get('/api/admin/migrare_fortata')
@token_required
@admin_required
def run_migration():
    con = get_conn()
    cur = con.cursor()

    # 1. Luăm toți părinții care au date în coloana veche 'copii'
    # Aceasta este "legătura cu partea veche" de care întrebai
    cur.execute("SELECT id, copii FROM utilizatori WHERE rol = 'Parinte' AND copii IS NOT NULL")
    parinti = cur.fetchall()

    count = 0

    for p in parinti:
        pid = p['id']
        raw_json = p['copii']

        try:
            # Încercăm să citim formatul vechi
            if not raw_json: continue
            children_list = json.loads(raw_json)

            if not isinstance(children_list, list): continue

            for child in children_list:
                nume = child.get('nume')
                grupa = child.get('grupa')
                gen = child.get('gen')
                varsta = child.get('varsta')  # În vechiul sistem era vârsta (int), nu data nașterii

                if not nume: continue

                # Evităm duplicatele: verificăm dacă copilul există deja în tabelul nou
                cur.execute("SELECT 1 FROM copii WHERE id_parinte = %s AND nume = %s", (pid, nume))
                if cur.fetchone(): continue

                # Convertim Vârsta Veche -> Data Nașterii Nouă (Estimare)
                dob = None
                if varsta and str(varsta).isdigit():
                    an_curent = datetime.datetime.now().year
                    # Estimăm că s-a născut pe 1 Ianuarie a anului respectiv
                    dob = f"{an_curent - int(varsta)}-01-01"

                # MUTAREA DATELOR: Scriem în tabelul nou SQL
                new_id = uuid.uuid4().hex

                # Insert în tabela COPII
                cur.execute("""
                    INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                """, (new_id, pid, nume, gen, grupa, dob))

                # Insert în tabela GRUPE (Sportivi pe Grupe)
                # Asta rezolvă vizibilitatea la antrenori
                if grupa:
                    # Găsim sau creăm ID-ul grupei
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
            print(f"Eroare la parintele ID {pid}: {e}")
            continue

    con.commit()
    return jsonify({
        "status": "success",
        "mesaj": f"Migrare completă! Am mutat {count} copii din vechiul sistem în cel nou."
    })