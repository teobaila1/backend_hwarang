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
        
        query = """
            -- 1. Sportivii cu cont propriu (rol 'Sportiv')
            SELECT 
                u.id::text as id, 
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
                WHERE sportiv_id::text = u.id::text
                ORDER BY data_examen DESC, id DESC LIMIT 1
            ) e ON true
            WHERE u.rol = 'Sportiv' AND COALESCE(p.activ, true) = true

            UNION ALL

            -- 2. Copiii afiliați părinților
            SELECT 
                c.id::text as id, 
                c.nume as nume_complet, 
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
                WHERE sportiv_id::text = c.id::text
                ORDER BY data_examen DESC, id DESC LIMIT 1
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
                eligibil_timp = True # Dacă nu a dat niciun examen, e eligibil ca timp

            rezultate.append({
                "id": s['id'],
                "nume": s['nume_complet'] or "Fără Nume",
                "cnp": s['cnp'] or "Necompletat", 
                "centura": s['centura_curenta'] or "10 Gup - Albă",
                "data_ultimului_examen": s['ultima_gradare'].strftime('%d.%m.%Y') if s['ultima_gradare'] else "Niciun examen",
                "luni_trecute": luni_trecute,
                "este_eligibil": eligibil_timp,
                "feedback": s['feedback_antrenor'],
                "tip": s['tip_inregistrare']
            })

        return jsonify(rezultate), 200

    except Exception as e:
        print(f"[EROARE SQL GET ELIGIBILITATE]: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()


# Rută nouă pentru actualizarea datelor personale ale sportivului
@exams_bp.route('/api/sportivi/actualizeaza', methods=['PUT'])
@token_required
def actualizeaza_sportiv():
    conn = get_conn()
    cur = None
    try:
        data = request.json
        sportiv_id = data.get('id')
        tip = data.get('tip') # 'utilizator' sau 'copil'
        nume = data.get('nume')
        cnp = data.get('cnp')

        if not sportiv_id or not nume:
            return jsonify({"status": "error", "message": "ID-ul și numele sunt obligatorii!"}), 400

        cur = conn.cursor()

        if tip == 'utilizator':
            # Actualizăm numele în utilizatori
            cur.execute("UPDATE utilizatori SET nume_complet = %s WHERE id = %s", (nume, int(sportiv_id)))
            # Actualizăm sau inserăm CNP-ul în profil_sportiv
            cur.execute("""
                INSERT INTO profil_sportiv (utilizator_id, cnp) VALUES (%s, %s)
                ON CONFLICT (utilizator_id) DO UPDATE SET cnp = EXCLUDED.cnp
            """, (int(sportiv_id), cnp))
        else:
            # Actualizăm în tabela copii (numele)
            cur.execute("UPDATE copii SET nume = %s WHERE id::text = %s", (nume, sportiv_id))
            # Notă: Dacă ai adăugat o coloană de cnp și în tabela copii, poți face update și acolo.

        conn.commit()
        return jsonify({"status": "success", "message": "Datele au fost actualizate cu succes!"}), 200

    except Exception as e:
        if conn: conn.rollback()
        print(f"[EROARE ACTUALIZARE SPORTIV]: {str(e)}")
        return jsonify({"status": "error", "message": "Eroare la actualizarea datelor."}), 500
    finally:
        if cur: cur.close()
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
        data_examen = data.get('data_examen') 
        feedback = data.get('feedback', '')

        if not sportiv_id or not centura_obtinuta or not data_examen:
            return jsonify({"status": "error", "message": "Date incomplete. Sportivul, centura și data sunt obligatorii."}), 400

        cur = conn.cursor()
        
        query = """
            INSERT INTO examene_centura 
            (sportiv_id, centura_obtinuta, data_examen, feedback_antrenor)
            VALUES (%s, %s, %s, %s)
        """
        # Salvăm sportiv_id ca string/text pentru a suporta atât int, cât și UUID
        cur.execute(query, (str(sportiv_id), centura_obtinuta, data_examen, feedback))
        conn.commit()
        
        return jsonify({"status": "success", "message": "Examenul a fost salvat cu succes!"}), 201

    except Exception as e:
        if conn: conn.rollback()
        print(f"[EROARE SALVARE EXAMEN]: {str(e)}")
        return jsonify({"status": "error", "message": "Eroare la salvarea examenului."}), 500
    finally:
        if cur: cur.close()
        if conn: conn.close()