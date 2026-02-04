from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

admin_diagnostic_bp = Blueprint('admin_diagnostic', __name__)

@admin_diagnostic_bp.get("/api/admin/diagnostic-date")
@token_required
def get_diagnostic_report():
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403

    con = get_conn()
    report = {
        "orfani": [],
        "date_incomplete": [],
        "errors": []
    }

    try:
        cur = con.cursor()

        # TEST 1: CĂUTĂM COPII ORFANI (Folosind numele corect: id_parinte)
        try:
            cur.execute("""
                SELECT c.id, c.nume, c.id_parinte 
                FROM copii c 
                LEFT JOIN utilizatori u ON c.id_parinte = u.id 
                WHERE u.id IS NULL;
            """)
            report["orfani"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            report["errors"].append(f"Eroare la orfani: {str(e)}")

        # TEST 2: DATE INCOMPLETE (Verificăm doar data_nasterii momentan)
        try:
            # Am scos cnp/grad ca să nu crape dacă nu există coloanele
            cur.execute("""
                SELECT id, nume 
                FROM copii 
                WHERE data_nasterii IS NULL;
            """)
            report["date_incomplete"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            report["errors"].append(f"Eroare la date incomplete: {str(e)}")

        return jsonify({
            "status": "success",
            "report": report
        }), 200

    except Exception as e:
        return jsonify({"status": "critical_error", "message": str(e)}), 500
    finally:
        con.close()