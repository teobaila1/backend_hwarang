from flask import Blueprint, jsonify, request
from datetime import datetime
import psycopg2
import psycopg2.extras
from backend.config import get_conn
from backend.accounts.decorators import token_required

exams_bp = Blueprint('exams', __name__)

@exams_bp.route('/api/sportivi/eligibilitate', methods=['GET'])
@token_required
def get_eligibilitate_sportivi():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Această interogare aduce ÎMPREUNĂ sportivii direcți și copiii părinților
        query = """
            -- 1. Sportivii cu cont propriu (rol 'Sportiv')
            SELECT 
                u.id, 
                u.nume_complet,
                p.cnp,
                p.activ,
                e.centura_obtinuta as centura_curenta,
                e.data_examen as ultima_gradare,
                e.feedback_antrenor,
                'utilizator' as tip_inregistrare
            FROM utilizatori u
            LEFT JOIN profil_sportiv p ON u.id = p.utilizator_id
            LEFT JOIN LATERAL (
                SELECT centura_obtinuta, data_examen, feedback_antrenor
                FROM examene_centura
                WHERE sportiv_id = u.id
                ORDER BY data_examen DESC LIMIT 1
            ) e ON true
            WHERE u.rol = 'Sportiv' AND COALESCE(p.activ, true) = true

            UNION ALL

            -- 2. Copiii afiliați părinților (fără CNP în tabelă, tratat ca NULL)
            SELECT 
                c.id, 
                c.nume as nume_complet, -- Asigură-te că în tabela copii coloana de nume se numește 'nume'
                NULL::varchar as cnp, 
                true as activ,
                e.centura_obtinuta as centura_curenta,
                e.data_examen as ultima_gradare,
                e.feedback_antrenor,
                'copil' as tip_inregistrare
            FROM copii c
            LEFT JOIN LATERAL (
                SELECT centura_obtinuta, data_examen, feedback_antrenor
                FROM examene_centura
                WHERE sportiv_id = c.id
                ORDER BY data_examen DESC LIMIT 1
            ) e ON true
        """
        cur.execute(query)
        sportivi = cur.fetchall()

        rezultate = []
        azi = datetime.today().date()

        for s in sportivi:
            luni_trecute = 0
            eligibil_timp = False
            
            if s['ultima_gradare']:
                luni_trecute = (azi.year - s['ultima_gradare'].year) * 12 + (azi.month - s['ultima_gradare'].month)
                if luni_trecute >= 3:
                    eligibil_timp = True
            else:
                eligibil_timp = True

            rezultate.append({
                "id": s['id'],
                "nume": s['nume_complet'] or "Fără Nume",
                "cnp": s['cnp'] or "Necompletat", 
                "prezente": 0, 
                "centura": s['centura_curenta'] or "10 Gup - Albă",
                "data_ultimului_examen": s['ultima_gradare'].strftime('%d.%m.%Y') if s['ultima_gradare'] else "Niciun examen",
                "luni_trecute": luni_trecute,
                "este_eligibil": eligibil_timp,
                "feedback": s['feedback_antrenor'],
                "tip": s['tip_inregistrare'] # Să știi dacă e sportiv independent sau copil de părinte
            })

        return jsonify(rezultate), 200

    except Exception as e:
        print(f"[EROARE SQL GET ELIGIBILITATE]: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()



@exams_bp.route('/api/sportivi/examen/salvare', methods=['POST'])
@token_required
def salveaza_examen():
    conn = get_conn()
    cur = None
    try:
        data = request.json
        sportiv_id = data.get('sportiv_id')
        centura_obtinuta = data.get('centura')
        data_examen = data.get('data_examen') # Format așteptat: YYYY-MM-DD
        prezente = data.get('prezente', 0)
        feedback = data.get('feedback', '')

        # Validare de bază
        if not sportiv_id or not centura_obtinuta or not data_examen:
            return jsonify({"status": "error", "message": "Date incomplete. Sportivul, centura și data sunt obligatorii."}), 400

        cur = conn.cursor()
        
        # Inserăm noul examen în istoric
        query = """
            INSERT INTO examene_centura 
            (sportiv_id, centura_obtinuta, data_examen, prezente_la_momentul_respectiv, feedback_antrenor)
            VALUES (%s, %s, %s, %s, %s)
        """
        cur.execute(query, (sportiv_id, centura_obtinuta, data_examen, prezente, feedback))
        
        # OBLIGATORIU: Salvăm modificările în baza de date
        conn.commit()
        
        return jsonify({"status": "success", "message": "Examenul a fost salvat cu succes!"}), 201

    except Exception as e:
        if conn: conn.rollback() # Anulăm tranzacția în caz de eroare
        print(f"[EROARE SALVARE EXAMEN]: {str(e)}")
        return jsonify({"status": "error", "message": "Eroare la salvarea examenului."}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()