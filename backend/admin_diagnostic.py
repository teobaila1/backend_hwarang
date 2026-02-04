from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

admin_diagnostic_bp = Blueprint('admin_diagnostic', __name__)

@admin_diagnostic_bp.get("/api/admin/diagnostic-date")
@token_required
def get_diagnostic_report():
    # Verificăm dacă utilizatorul este admin
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis! Doar adminul poate accesa acest raport."}), 403

    con = get_conn()
    report = {
        "orfani": [],          # Copii care au un parent_id care nu mai există
        "date_incomplete": [], # Copii cărora le lipsesc date obligatorii pentru concurs
        "roluri_incorecte": [] # Utilizatori care au copii dar nu au rolul de 'Parinte'
    }

    try:
        cur = con.cursor()

        # 1. Identificăm copiii cu parent_id inexistent în tabela utilizatori
        cur.execute("""
            SELECT c.id, c.nume, c.parent_id 
            FROM copii c 
            LEFT JOIN utilizatori u ON c.parent_id = u.id 
            WHERE u.id IS NULL;
        """)
        report["orfani"] = [dict(r) for r in cur.fetchall()]

        # 2. Identificăm sportivii cu date incomplete (CNP, Grad, Data Nașterii)
        cur.execute("""
            SELECT id, nume, parent_id 
            FROM copii 
            WHERE cnp IS NULL OR grad IS NULL OR data_nasterii IS NULL;
        """)
        report["date_incomplete"] = [dict(r) for r in cur.fetchall()]

        # 3. Identificăm părinții care au copii dar nu au rolul corect
        cur.execute("""
            SELECT id, username, rol 
            FROM utilizatori 
            WHERE id IN (SELECT DISTINCT parent_id FROM copii) 
            AND rol NOT IN ('Parinte', 'admin');
        """)
        report["roluri_incorecte"] = [dict(r) for r in cur.fetchall()]

        return jsonify({
            "status": "success",
            "report": report
        }), 200


    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()