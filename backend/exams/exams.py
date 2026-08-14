from flask import Blueprint, jsonify
from datetime import datetime
from dateutil.relativedelta import relativedelta # Foarte utilă pentru a calcula diferența în luni
from backend.config import get_conn
from backend.accounts.decorators import token_required

exams_bp = Blueprint('exams', __name__)

@exams_bp.route('/api/sportivi/eligibilitate', methods=['GET'])
@token_required
def get_eligibilitate_sportivi():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Interogare care aduce sportivii, prezențele lor totale și datele ultimului examen
        # Presupunem că ai o funcție sau un view care îți dă numărul de prezențe curente
        query = """
            SELECT 
                u.id, u.nume_complet, u.cnp,
                e.centura_obtinuta as centura_curenta,
                e.data_examen as ultima_gradare,
                u.prezente_curente, -- Camp ipotetic calculat din pontaj
                e.feedback_antrenor
            FROM utilizatori u
            LEFT JOIN LATERAL (
                SELECT centura_obtinuta, data_examen, feedback_antrenor
                FROM examene_centura
                WHERE sportiv_id = u.id
                ORDER BY data_examen DESC LIMIT 1
            ) e ON true
            WHERE u.rol IN ('Sportiv', 'Parinte') AND u.activ = true
        """
        cur.execute(query)
        sportivi = cur.fetchall()

        rezultate = []
        azi = datetime.today().date()

        for s in sportivi:
            luni_trecute = 0
            eligibil_timp = False
            eligibil_prezente = False
            
            if s['ultima_gradare']:
                diferenta = relativedelta(azi, s['ultima_gradare'])
                luni_trecute = diferenta.years * 12 + diferenta.months
                
                # Regula: între 3 și 6 luni
                if luni_trecute >= 3:
                    eligibil_timp = True

            # Regula: minim 24 de prezențe de la ultimul examen (exemplu)
            prezente = s.get('prezente_curente', 0)
            if prezente >= 24:
                eligibil_prezente = True

            rezultate.append({
                "id": s['id'],
                "nume": s['nume_complet'],
                "cnp": s['cnp'],
                "centura": s['centura_curenta'] or "Centura Albă (10 Gup)",
                "data_ultimului_examen": s['ultima_gradare'].strftime('%d.%m.%Y') if s['ultima_gradare'] else "Niciun examen",
                "luni_trecute": luni_trecute,
                "prezente": prezente,
                "este_eligibil": eligibil_timp and eligibil_prezente,
                "feedback": s['feedback_antrenor']
            })

        return jsonify(rezultate), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()