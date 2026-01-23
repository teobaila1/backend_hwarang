import psycopg2.extras
from flask import Blueprint, jsonify, request
from backend.config import get_conn
from backend.accounts.decorators import token_required

inscrierile_mele_bp = Blueprint('inscrierile_mele', __name__)


@inscrierile_mele_bp.get('/api/inscrierile_mele')
@token_required
def get_my_registrations():
    user_id = request.user_id
    con = get_conn()
    try:
        # Folosim RealDictCursor ca sa fim SIGURI ca primim {"nume": "Ion", ...} si nu (1, "Ion", ...)
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Aflăm cine face cererea
        cur.execute("SELECT username, email, rol, nume_complet FROM utilizatori WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Utilizator negăsit."}), 404

        rol = user['rol']
        username = user['username']
        email = user['email']
        nume_complet = user['nume_complet']

        results = []

        # --- LOGICA PENTRU PĂRINȚI ---
        if rol == 'Parinte':
            # Găsim copiii
            cur.execute("SELECT nume FROM copii WHERE id_parinte = %s", (user_id,))
            kids_rows = cur.fetchall()

            nume_copii = [row['nume'] for row in kids_rows if row['nume']]

            if nume_copii:
                placeholders = ','.join(['%s'] * len(nume_copii))
                # ATENTIE: Am scos 'created_at' momentan pentru a evita erori daca coloana nu exista
                # Daca tabela ta are coloana 'data_inscriere' in loc de 'created_at', modifica mai jos
                sql = f"""
                    SELECT id, concurs, nume, categorie_varsta, probe
                    FROM inscrieri_concursuri 
                    WHERE nume IN ({placeholders})
                """
                cur.execute(sql, tuple(nume_copii))
                results = cur.fetchall()

        # --- LOGICA PENTRU SPORTIVI ---
        else:
            cur.execute("""
                SELECT id, concurs, nume, categorie_varsta, probe
                FROM inscrieri_concursuri 
                WHERE LOWER(username) = LOWER(%s) 
                   OR LOWER(email) = LOWER(%s)
                   OR LOWER(nume) = LOWER(%s)
            """, (username, email, nume_complet))
            results = cur.fetchall()

        # Formatăm datele
        data = []
        for r in results:
            # Încercăm să luăm data, dacă există coloana created_at sau data_inscriere, altfel punem azi
            data_add = "N/A"
            if 'created_at' in r and r['created_at']:
                data_add = str(r['created_at'].strftime('%Y-%m-%d'))

            data.append({
                "id": r['id'],
                "concurs": r['concurs'],
                "nume_sportiv": r['nume'],
                "categorie": r['categorie_varsta'],
                "probe": r['probe'],
                "data_inscriere": data_add
            })

        return jsonify({"status": "success", "data": data}), 200

    except Exception as e:
        # AICI ESTE CHEIA: Printam eroarea in consola serverului ca sa vedem ce are
        print(f"!!!!!!!! EROARE SERVER INSCRIERI: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()