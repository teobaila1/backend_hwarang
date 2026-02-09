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
        # Folosim RealDictCursor pentru a accesa coloanele prin nume
        cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Identificăm utilizatorul
        cur.execute("SELECT username, email, rol, nume_complet FROM utilizatori WHERE id = %s", (user_id,))
        user = cur.fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Utilizator negăsit."}), 404

        rol = user['rol']
        username = user['username']
        email = user['email']
        nume_complet = user['nume_complet'] or ""

        results = []

        # --- LOGICA NOUĂ (REPARATĂ) ---

        # Lista de nume pe care le căutăm (pe lângă username/email)
        nume_de_cautat = [nume_complet] if nume_complet else []

        if rol == 'Parinte':
            # Găsim și numele copiilor din dashboard, ca să fim siguri
            cur.execute("SELECT nume FROM copii WHERE id_parinte = %s", (user_id,))
            kids_rows = cur.fetchall()
            for row in kids_rows:
                if row['nume']:
                    nume_de_cautat.append(row['nume'])

        # Construim clauza SQL dinamic
        # Căutăm înscrieri unde:
        # 1. Username-ul celui care a înscris e al meu
        # 2. SAU Email-ul e al meu
        # 3. SAU Numele sportivului e în lista mea de copii (sau numele meu)

        sql_query = """
            SELECT id, concurs, nume, categorie_varsta, probe, created_at
            FROM inscrieri_concursuri 
            WHERE LOWER(username) = LOWER(%s) 
               OR LOWER(email) = LOWER(%s)
        """

        params = [username, email]

        if nume_de_cautat:
            # Adăugăm OR nume IN (...)
            placeholders = ','.join(['%s'] * len(nume_de_cautat))
            sql_query += f" OR nume IN ({placeholders})"
            params.extend(nume_de_cautat)

        sql_query += " ORDER BY created_at DESC"

        cur.execute(sql_query, tuple(params))
        results = cur.fetchall()

        # 3. Formatăm datele pentru Frontend
        data = []
        for r in results:
            # Formatare dată: YYYY-MM-DD (ex: 2024-05-20)
            data_add = "N/A"
            if r.get('created_at'):
                data_add = r['created_at'].strftime('%Y-%m-%d')

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
        print(f"!!!!!!!! EROARE SERVER INSCRIERI: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()