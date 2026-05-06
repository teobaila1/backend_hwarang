from flask import Blueprint, request, jsonify
# Asigură-te că ai importat decoratorul tău pentru token (ex: @token_required)


inscriere_evenimente_bp = Blueprint('inscriere_evenimente', __name__)


@inscriere_evenimente_bp.route('/api/calendar/evenimente/<int:eveniment_id>/inscriere', methods=['POST'])
@token_required  # Decoratorul tău care verifică dacă e logat
def inscrie_la_eveniment(current_user, eveniment_id):
    try:
        data = request.json
        sportivi_ids = data.get('sportivi_ids', [])
        
        # Aici luăm ID-ul clubului din token-ul utilizatorului logat.
        # Ajustează 'id' sau 'club_id' în funcție de cum e salvat în token-ul tău!
        club_id = current_user.get('id') 

        # 1. Ștergem toate înscrierile anterioare ale ACESTUI club pentru ACEST eveniment
        # Astfel, dacă antrenorul a debifat pe cineva, acea persoană va fi eliminată automat.
        supabase.table('inscrieri_evenimente') \
            .delete() \
            .eq('eveniment_id', eveniment_id) \
            .eq('club_id', club_id) \
            .execute()

        # 2. Inserăm lista nouă de sportivi (dacă a selectat pe cineva)
        if sportivi_ids:
            insert_data = []
            for sp_id in sportivi_ids:
                insert_data.append({
                    "eveniment_id": eveniment_id,
                    "sportiv_id": sp_id,
                    "club_id": club_id
                })
            
            # Trimitem toată lista dintr-un singur foc în baza de date
            supabase.table('inscrieri_evenimente').insert(insert_data).execute()

        return jsonify({"message": "Înscriere salvată cu succes!"}), 200

    except Exception as e:
        print(f"Eroare la inscriere eveniment: {e}")
        return jsonify({"error": "A apărut o eroare la salvarea datelor."}), 500