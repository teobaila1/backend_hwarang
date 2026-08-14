from flask import Blueprint, jsonify, request
from datetime import datetime, date
import psycopg2
import psycopg2.extras
from backend.config import get_conn
from backend.accounts.decorators import token_required

exams_bp = Blueprint('exams', __name__)

def calculeaza_varsta_si_categorie(cnp, data_nasterii_db):
    dob = None
    
    # 1. Folosim data nașterii din baza de date dacă există
    if data_nasterii_db:
        dob = data_nasterii_db
    # 2. Altfel, dacă avem CNP valid de 13 caractere, extragem data nașterii din el
    elif cnp and len(cnp) == 13 and cnp.isdigit():
        s = int(cnp[0])
        an_pre = 1900
        if s in [1, 2]: an_pre = 1900
        elif s in [3, 4]: an_pre = 1800
        elif s in [5, 6]: an_pre = 2000
        elif s in [7, 8]: an_pre = 1900
        
        an = an_pre + int(cnp[1:3])
        luna = int(cnp[3:5])
        zi = int(cnp[5:7])
        try:
            dob = date(an, luna, zi)
        except:
            dob = None

    if not dob:
        return "Nespecificat", 0

    azi = date.today()
    age = azi.year - dob.year - ((azi.month, azi.day) < (dob.month, dob.day))

    if age >= 18:
        categorie = "SENIOR"
    elif age >= 15:
        categorie = "JUNIOR I"
    elif age >= 12:
        categorie = "JUNIOR II"
    elif age >= 9:
        categorie = "JUNIOR III"
    else:
        categorie = "COPII"

    return categorie, age

def calculeaza_timp_scurs(ultima_gradare):
    if not ultima_gradare:
        return 0, 0, "Niciun examen", True

    azi = date.today()
    delta = azi - ultima_gradare
    zile_totale = delta.days

    if zile_totale < 0:
        return 0, 0, "Data în viitor", False

    luni = (azi.year - ultima_gradare.year) * 12 + (azi.month - ultima_gradare.month)
    if azi.day < ultima_gradare.day:
        luni -= 1

    an_tinta = ultima_gradare.year + (ultima_gradare.month - 1 + luni) // 12
    luna_tinta = (ultima_gradare.month - 1 + luni) % 12 + 1
    
    import calendar
    last_day = calendar.monthrange(an_tinta, luna_tinta)[1]
    zi_tinta = min(ultima_gradare.day, last_day)
    
    data_intermediare = date(an_tinta, luna_tinta, zi_tinta)
    zile_ramase = (azi - data_intermediare).days

    eligibil = luni >= 3
    text_timp = f"{luni} luni și {zile_ramase} zile scurse"

    return luni, zile_ramase, text_timp, eligibil


@exams_bp.route('/api/sportivi/eligibilitate', methods=['GET'])
@token_required
def get_eligibilitate_sportivi():
    conn = get_conn()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        query = """
            -- 1. Sportivii cu cont propriu (preluăm data_nasterii din profil_sportiv sau utilizatori)
            SELECT 
                u.id::text as id, 
                u.nume_complet,
                p.cnp,
                COALESCE(p.data_nasterii, u.data_nasterii) as data_nasterii,
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

            -- 2. Copiii afiliați părinților (preluăm data_nasterii din tabela copii)
            SELECT 
                c.id::text as id, 
                c.nume as nume_complet, 
                NULL::varchar as cnp, 
                c.data_nasterii,
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

        for s in sportivi:
            luni, zile, text_timp, eligibil_timp = calculeaza_timp_scurs(s['ultima_gradare'])
            categorie, varsta = calculeaza_varsta_si_categorie(s['cnp'], s['data_nasterii'])

            rezultate.append({
                "id": s['id'],
                "nume": s['nume_complet'] or "Fără Nume",
                "cnp": s['cnp'] or "Necompletat", 
                "data_nasterii": s['data_nasterii'].strftime('%Y-%m-%d') if s['data_nasterii'] else "",
                "centura": s['centura_curenta'] or "10 Gup - Albă",
                "data_ultimului_examen": s['ultima_gradare'].strftime('%d.%m.%Y') if s['ultima_gradare'] else "Niciun examen",
                "luni_trecute": luni,
                "zile_trecute": zile,
                "text_timp": text_timp,
                "este_eligibil": eligibil_timp,
                "feedback": s['feedback_antrenor'],
                "tip": s['tip_inregistrare'],
                "categorie": categorie,
                "varsta": varsta
            })

        return jsonify(rezultate), 200

    except Exception as e:
        print(f"[EROARE SQL GET ELIGIBILITATE]: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn: conn.close()


@exams_bp.route('/api/sportivi/actualizeaza', methods=['PUT'])
@token_required
def actualizeaza_sportiv():
    conn = get_conn()
    cur = None
    try:
        data = request.json
        sportiv_id = data.get('id')
        tip = data.get('tip') 
        nume = data.get('nume')
        cnp = data.get('cnp')
        data_nasterii = data.get('data_nasterii') or None

        if not sportiv_id or not nume:
            return jsonify({"status": "error", "message": "ID-ul și numele sunt obligatorii!"}), 400

        cur = conn.cursor()

        if tip == 'utilizator':
            cur.execute("UPDATE utilizatori SET nume_complet = %s WHERE id = %s", (nume, int(sportiv_id)))
            cur.execute("""
                INSERT INTO profil_sportiv (utilizator_id, cnp, data_nasterii) 
                VALUES (%s, %s, %s)
                ON CONFLICT (utilizator_id) 
                DO UPDATE SET cnp = EXCLUDED.cnp, data_nasterii = EXCLUDED.data_nasterii
            """, (int(sportiv_id), cnp, data_nasterii))
        else:
            cur.execute("UPDATE copii SET nume = %s, data_nasterii = %s WHERE id::text = %s", (nume, data_nasterii, sportiv_id))

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