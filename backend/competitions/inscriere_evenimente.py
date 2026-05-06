from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

inscriere_evenimente_bp = Blueprint('inscriere_evenimente', __name__)

@inscriere_evenimente_bp.route('/api/calendar/evenimente/<int:eveniment_id>/inscriere', methods=['POST'])
@token_required
def inscrie_la_eveniment(current_user, eveniment_id):
    conn = None
    cursor = None
    try:
        data = request.json
        sportivi_ids = data.get('sportivi_ids', [])
        inscrieri_manuale = data.get('inscrieri_manuale', []) # Noua lista din React
        
        club_id = current_user.get('id') 

        conn = get_conn()
        cursor = conn.cursor()

        # 1. Ștergem toate înscrierile anterioare pentru ACEST user la ACEST eveniment
        delete_query = """
            DELETE FROM inscrieri_evenimente 
            WHERE eveniment_id = %s AND club_id = %s
        """
        cursor.execute(delete_query, (eveniment_id, club_id))

        # 2. Inserăm sportivii bifati (cei cu ID)
        if sportivi_ids:
            insert_ids_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, sportiv_id, club_id)
                VALUES (%s, %s, %s)
            """
            insert_ids_data = [(eveniment_id, sp_id, club_id) for sp_id in sportivi_ids]
            cursor.executemany(insert_ids_query, insert_ids_data)

        # 3. Inserăm sportivii adăugați manual (fără ID, doar cu nume)
        if inscrieri_manuale:
            insert_manual_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, club_id, nume_manual, prenume_manual)
                VALUES (%s, %s, %s, %s)
            """
            insert_manual_data = [
                (eveniment_id, club_id, p.get('nume'), p.get('prenume')) 
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