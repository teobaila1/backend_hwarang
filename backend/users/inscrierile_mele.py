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
        cur = con.cursor()

        # 1. Aflăm cine face cererea (Rol, Nume, Email)
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
            # A. Găsim numele copiilor acestui părinte
            cur.execute("SELECT nume FROM copii WHERE id_parinte = %s", (user_id,))
            kids_rows = cur.fetchall()

            nume_copii = [row['nume'] for row in kids_rows if row['nume']]

            if nume_copii:
                # B. Căutăm înscrierile care au numele copilului în coloana 'nume'
                # Folosim o clauză IN dinamică
                placeholders = ','.join(['%s'] * len(nume_copii))
                sql = f"""
                    SELECT id, concurs, nume, categorie_varsta, probe, created_at
                    FROM inscrieri_concursuri
                    WHERE nume IN ({placeholders})
                    ORDER BY created_at DESC
                """
                cur.execute(sql, tuple(nume_copii))
                results = cur.fetchall()

        # --- LOGICA PENTRU SPORTIVI (sau Antrenori care participă) ---
        else:
            # Căutăm după username, email sau nume complet
            cur.execute("""
                SELECT id, concurs, nume, categorie_varsta, probe, created_at
                FROM inscrieri_concursuri
                WHERE LOWER(username) = LOWER(%s)
                   OR LOWER(email) = LOWER(%s)
                   OR LOWER(nume) = LOWER(%s)
                ORDER BY created_at DESC
            """, (username, email, nume_complet))
            results = cur.fetchall()

        # Formatăm datele frumos pentru frontend
        data = []
        for r in results:
            data.append({
                "id": r['id'],
                "concurs": r['concurs'],
                "nume_sportiv": r['nume'],
                "categorie": r['categorie_varsta'],
                "probe": r['probe'],
                "data_inscriere": str(r['created_at'].strftime('%Y-%m-%d')) if r['created_at'] else "N/A"
            })

        return jsonify({"status": "success", "data": data}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()