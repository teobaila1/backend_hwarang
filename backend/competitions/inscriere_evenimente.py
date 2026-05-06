from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
import jwt
import os

inscriere_evenimente_bp = Blueprint('inscriere_evenimente', __name__)

@inscriere_evenimente_bp.route('/api/calendar/evenimente/<int:eveniment_id>/inscriere', methods=['POST'])
@token_required
def inscrie_la_eveniment(eveniment_id):
    conn = None
    cursor = None
    try:
        token = request.headers.get('x-access-token')
        SECRET_KEY = os.getenv("SECRET_KEY", "schimba-asta-in-productie")
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        club_id = decoded_token.get('id')

        data = request.json
        # Acum primim o listă de dicționare, nu doar ID-uri simple
        sportivi_selectati = data.get('sportivi_selectati', []) 
        inscrieri_manuale = data.get('inscrieri_manuale', []) 
        
        conn = get_conn()
        cursor = conn.cursor()

        # Ștergem înscrierile anterioare
        delete_query = "DELETE FROM inscrieri_evenimente WHERE eveniment_id = %s AND club_id = %s"
        cursor.execute(delete_query, (eveniment_id, club_id))

        # Inserăm sportivii din profil (cu grad curent și viitor)
        if sportivi_selectati:
            insert_ids_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, sportiv_id, club_id, grad_curent, grad_viitor)
                VALUES (%s, %s, %s, %s, %s)
            """
            insert_ids_data = [
                (eveniment_id, sp.get('id'), club_id, sp.get('grad_curent'), sp.get('grad_viitor')) 
                for sp in sportivi_selectati
            ]
            cursor.executemany(insert_ids_query, insert_ids_data)

        # Inserăm persoanele adăugate manual
        if inscrieri_manuale:
            insert_manual_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, club_id, nume_manual, prenume_manual, grad_curent, grad_viitor)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            insert_manual_data = [
                (eveniment_id, club_id, p.get('nume'), p.get('prenume'), p.get('grad_curent'), p.get('grad_viitor')) 
                for p in inscrieri_manuale
            ]
            cursor.executemany(insert_manual_query, insert_manual_data)

        conn.commit()
        return jsonify({"message": "Înscriere salvată cu succes!"}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Eroare la inscriere eveniment: {repr(e)}")
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

        # Citim acum noile coloane: grad_curent și grad_viitor
        query = """
            SELECT 
                COALESCE(s.nume, ie.nume_manual) AS nume,
                COALESCE(ie.prenume_manual, '') AS prenume,
                ie.grad_curent,
                ie.grad_viitor,
                CASE WHEN ie.sportiv_id IS NOT NULL THEN 'Profil' ELSE 'Manual' END as tip_inscriere
            FROM inscrieri_evenimente ie
            LEFT JOIN copii s ON REPLACE(ie.sportiv_id::text, '-', '') = s.id
            WHERE ie.eveniment_id = %s
            ORDER BY nume ASC
        """
        cursor.execute(query, (eveniment_id,))
        randuri = cursor.fetchall()

        inscrieri = []
        for rand in randuri:
            if isinstance(rand, dict):
                inscrieri.append({
                    "nume": rand.get("nume"),
                    "prenume": rand.get("prenume"),
                    "grad_curent": rand.get("grad_curent"),
                    "grad_viitor": rand.get("grad_viitor"),
                    "tip_inscriere": rand.get("tip_inscriere")
                })
            else:
                inscrieri.append({
                    "nume": rand[0],
                    "prenume": rand[1],
                    "grad_curent": rand[2],
                    "grad_viitor": rand[3],
                    "tip_inscriere": rand[4]
                })

        return jsonify(inscrieri), 200

    except Exception as e:
        print(f"Eroare la citire inscrieri: {repr(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()