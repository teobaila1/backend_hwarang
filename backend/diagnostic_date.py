from backend.config import get_conn

def ruleaza_diagnostic():
    con = get_conn()
    try:
        cur = con.cursor()
        print("=== START DIAGNOSTIC DATE HWARANG ===\n")

        # 1. Căutăm COPII fără PĂRINȚI (Orfani în baza de date)
        # Verificăm dacă parent_id din tabela copii mai există în tabela utilizatori
        cur.execute("""
            SELECT c.id, c.nume, c.parent_id 
            FROM copii c 
            LEFT JOIN utilizatori u ON c.parent_id = u.id 
            WHERE u.id IS NULL;
        """)
        orfani = cur.fetchall()
        print(f"[!] Copii cu parent_id inexistent: {len(orfani)}")
        for o in orfani:
            print(f"    - Copil: {o['nume']} (ID: {o['id']}) are parent_id: {o['parent_id']} care NU există.")

        # 2. Căutăm date incomplete care blochează înscrierea la concursuri
        # Presupunem că CNP, Grad și Data Nașterii sunt acum obligatorii
        cur.execute("""
            SELECT id, nume, parent_id 
            FROM copii 
            WHERE cnp IS NULL OR grad IS NULL OR data_nasterii IS NULL;
        """)
        incompleti = cur.fetchall()
        print(f"\n[!] Profiluri de copii cu date lipsă (CNP/Grad/DataNasterii): {len(incompleti)}")
        for i in incompleti:
            print(f"    - Copil: {i['nume']} (ID: {i['id']}) - Are date incomplete.")

        # 3. Verificăm dacă există părinți care au cont dar nu au rolul de 'Parinte' setat corect
        cur.execute("""
            SELECT id, username, rol 
            FROM utilizatori 
            WHERE id IN (SELECT DISTINCT parent_id FROM copii) AND rol != 'Parinte' AND rol != 'admin';
        """)
        roluri_gresite = cur.fetchall()
        print(f"\n[!] Utilizatori cu copii dar fără rol de 'Parinte': {len(roluri_gresite)}")
        for r in roluri_gresite:
            print(f"    - User: {r['username']} (ID: {r['id']}) are rolul: {r['rol']} (ar trebui să fie Parinte).")

        # 4. Căutăm duplicate rămase (Nume identic la același părinte)
        cur.execute("""
            SELECT nume, parent_id, COUNT(*) 
            FROM copii 
            GROUP BY nume, parent_id 
            HAVING COUNT(*) > 1;
        """)
        duplicate = cur.fetchall()
        print(f"\n[!] Posibile duplicate detectate: {len(duplicate)}")
        for d in duplicate:
            print(f"    - Copilul '{d['nume']}' apare de {d['count']} ori la părintele cu ID {d['parent_id']}.")

        print("\n=== DIAGNOSTIC FINALIZAT ===")

    except Exception as e:
        print(f"Eroare în timpul diagnosticului: {e}")
    finally:
        con.close()

if __name__ == "__main__":
    ruleaza_diagnostic()