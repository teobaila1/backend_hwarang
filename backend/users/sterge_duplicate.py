from flask import Blueprint, jsonify
from backend.config import get_conn

sterge_duplicate_bp = Blueprint('sterge_duplicate', __name__)


@sterge_duplicate_bp.get('/api/admin/sterge_duplicate')
def sterge_duplicate():
    con = get_conn()
    cur = con.cursor()

    try:
        # SQL Magic: Păstrează doar un rând pentru fiecare pereche (grupă, copil)
        # Șterge rândurile care au ID mai mare (adică cele adăugate ulterior, duplicatele)
        cur.execute("""
            DELETE FROM sportivi_pe_grupe a 
            USING sportivi_pe_grupe b
            WHERE a.id > b.id 
            AND a.id_grupa = b.id_grupa 
            AND a.id_sportiv_copil = b.id_sportiv_copil
            AND a.id_sportiv_copil IS NOT NULL;
        """)

        # Facem la fel și pentru sportivi adulți
        cur.execute("""
            DELETE FROM sportivi_pe_grupe a 
            USING sportivi_pe_grupe b
            WHERE a.id > b.id 
            AND a.id_grupa = b.id_grupa 
            AND a.id_sportiv_user = b.id_sportiv_user
            AND a.id_sportiv_user IS NOT NULL;
        """)

        con.commit()
        return jsonify({"status": "success", "message": "Duplicatele au fost șterse!"})

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()