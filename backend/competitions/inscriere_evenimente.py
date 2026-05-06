from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
import jwt
import os

inscriere_evenimente_bp = Blueprint('inscriere_evenimente', __name__)

@inscriere_evenimente_bp.route('/api/calendar/evenimente/<int:eveniment_id>/inscriere', methods=['POST'])
@token_required  # Decoratorul tău protejează ruta (dă 401 dacă nu e logat)
def inscrie_la_eveniment(eveniment_id):  # <-- AM SCOS 'current_user' DE AICI
    conn = None
    cursor = None
    try:
        # --- 1. Extragem manual ID-ul utilizatorului din token ---
        token = request.headers.get('x-access-token')
        SECRET_KEY = os.getenv("SECRET_KEY", "schimba-asta-in-productie")
        
        # Decodăm token-ul pentru a afla ID-ul persoanei logate
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        club_id = decoded_token.get('id')  # Așa aflăm cine face acțiunea

        # --- 2. Preluăm datele trimise din React ---
        data = request.json
        sportivi_ids = data.get('sportivi_ids', [])
        inscrieri_manuale = data.get('inscrieri_manuale', []) 
        
        conn = get_conn()
        cursor = conn.cursor()

        # --- 3. Ștergem toate înscrierile anterioare pentru ACEST user la ACEST eveniment ---
        delete_query = """
            DELETE FROM inscrieri_evenimente 
            WHERE eveniment_id = %s AND club_id = %s
        """
        cursor.execute(delete_query, (eveniment_id, club_id))

        # --- 4. Inserăm sportivii bifați (cei cu ID din profil) ---
        if sportivi_ids:
            insert_ids_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, sportiv_id, club_id)
                VALUES (%s, %s, %s)
            """
            insert_ids_data = [(eveniment_id, sp_id, club_id) for sp_id in sportivi_ids]
            cursor.executemany(insert_ids_query, insert_ids_data)

        # --- 5. Inserăm persoanele adăugate manual (fără ID, cu Nume, Prenume și Grad) ---
        if inscrieri_manuale:
            insert_manual_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, club_id, nume_manual, prenume_manual, grad_manual)
                VALUES (%s, %s, %s, %s, %s)
            """
            insert_manual_data = [
                (eveniment_id, club_id, p.get('nume'), p.get('prenume'), p.get('grad')) 
                for p in inscrieri_manuale
            ]
            cursor.executemany(insert_manual_query, insert_manual_data)

        conn.commit()
        return jsonify({"message": "Înscriere salvată cu succes!"}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Eroare la inscriere eveniment: {e}")
        return jsonify({"error": "A apărut o eroare la salvarea datelor."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()





@inscriere_evenimente_bp.route('/api/calendar/evenimente/<int:eveniment_id>/inscrieri', methods=['GET'])
@token_required
def get_inscrieri_eveniment(eveniment_id):
    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor()

        # Această interogare combină datele din profiluri cu cele introduse manual.
        # ATENȚIE: Am presupus că tabelul tău cu copii se numește 'sportivi'. 
        # Dacă se numește altfel (ex: 'copii'), modifică cuvântul 'sportivi' de mai jos.
        query = """
            SELECT 
                COALESCE(s.nume, ie.nume_manual) AS nume,
                COALESCE(s.prenume, ie.prenume_manual) AS prenume,
                COALESCE(s.grad, ie.grad_manual) AS grad,
                CASE WHEN ie.sportiv_id IS NOT NULL THEN 'Profil' ELSE 'Manual' END as tip_inscriere
            FROM inscrieri_evenimente ie
            LEFT JOIN sportivi s ON ie.sportiv_id = s.id
            WHERE ie.eveniment_id = %s
            ORDER BY nume ASC
        """
        cursor.execute(query, (eveniment_id,))
        randuri = cursor.fetchall()

        # Formatăm rezultatul pentru React
        inscrieri = []
        for rand in randuri:
            inscrieri.append({
                "nume": rand[0],
                "prenume": rand[1],
                "grad": rand[2],
                "tip_inscriere": rand[3]
            })

        return jsonify(inscrieri), 200

    except Exception as e:
        print(f"Eroare la citire inscrieri: {e}")
        return jsonify({"error": "A apărut o eroare la preluarea datelor."}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()