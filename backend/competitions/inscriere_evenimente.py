from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

inscriere_evenimente_bp = Blueprint('inscriere_evenimente', __name__)

@inscriere_evenimente_bp.route('/api/calendar/evenimente/<int:eveniment_id>/inscriere', methods=['POST'])
@token_required  # Decoratorul tău care verifică dacă e logat
def inscrie_la_eveniment(current_user, eveniment_id):
    conn = None
    cursor = None
    try:
        data = request.json
        sportivi_ids = data.get('sportivi_ids', [])
        
        # Luăm ID-ul clubului din token-ul utilizatorului logat.
        club_id = current_user.get('id') 

        conn = get_conn()
        cursor = conn.cursor()

        # 1. Ștergem toate înscrierile anterioare ale ACESTUI club pentru ACEST eveniment
        # Astfel, dacă antrenorul a debifat pe cineva, acea persoană va fi eliminată automat.
        delete_query = """
            DELETE FROM inscrieri_evenimente 
            WHERE eveniment_id = %s AND club_id = %s
        """
        cursor.execute(delete_query, (eveniment_id, club_id))

        # 2. Inserăm lista nouă de sportivi (dacă a selectat pe cineva)
        if sportivi_ids:
            insert_query = """
                INSERT INTO inscrieri_evenimente (eveniment_id, sportiv_id, club_id)
                VALUES (%s, %s, %s)
            """
            # Pregătim o listă cu toate tuplurile pentru inserare
            insert_data = [(eveniment_id, sp_id, club_id) for sp_id in sportivi_ids]
            
            # Folosim executemany pentru a face o singură tranzacție rapidă către baza de date
            cursor.executemany(insert_query, insert_data)

        # Confirmăm schimbările în baza de date
        conn.commit()

        return jsonify({"message": "Înscriere salvată cu succes!"}), 200

    except Exception as e:
        # Dacă pică ceva pe parcurs, anulăm modificările (Rollback) ca să nu lăsăm date pe jumătate șterse
        if conn:
            conn.rollback()
        print(f"Eroare la inscriere eveniment: {e}")
        return jsonify({"error": "A apărut o eroare la salvarea datelor."}), 500
    finally:
        # Închidem mereu conexiunea la final
        if cursor:
            cursor.close()
        if conn:
            conn.close()