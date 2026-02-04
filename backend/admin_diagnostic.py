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
        "roluri_incorecte": [],
        "errors": [] # Aici vom salva erorile tehnice
    }

    try:
        cur = con.cursor()

        # TEST 1: COPII ORFANI (Verificăm separat să vedem unde crapă)
        try:
            # Verificăm întâi dacă există tabela 'utilizatori' sau 'users'
            cur.execute("SELECT to_regclass('public.utilizatori')")
            if cur.fetchone()[0] is None:
                report["errors"].append("Tabela 'utilizatori' NU există! Verifică numele (poate e 'users'?)")
            else:
                cur.execute("""
                    SELECT c.id, c.nume, c.parent_id 
                    FROM copii c 
                    LEFT JOIN utilizatori u ON c.parent_id = u.id 
                    WHERE u.id IS NULL;
                """)
                report["orfani"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            report["errors"].append(f"Eroare la verificarea orfanilor: {str(e)}")

        # TEST 2: DATE INCOMPLETE (Aici e riscul mare de nume greșit la coloane)
        try:
            # Încercăm o interogare simplă
            cur.execute("""
                SELECT id, nume, parent_id 
                FROM copii 
                WHERE cnp IS NULL OR grad IS NULL OR data_nasterii IS NULL;
            """)
            report["date_incomplete"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            # Dacă crapă, înseamnă că una din coloane are alt nume
            report["errors"].append(f"Eroare la date incomplete (posibil nume coloană greșit): {str(e)}")

        # TEST 3: ROLURI
        try:
            cur.execute("""
                SELECT id, username, rol 
                FROM utilizatori 
                WHERE id IN (SELECT DISTINCT parent_id FROM copii) 
                AND rol NOT IN ('Parinte', 'admin');
            """)
            report["roluri_incorecte"] = [dict(r) for r in cur.fetchall()]
        except Exception as e:
            report["errors"].append(f"Eroare la verificarea rolurilor: {str(e)}")

        # Returnăm 200 OK chiar dacă au fost erori interne, ca să le vedem în consolă
        return jsonify({
            "status": "success",
            "report": report
        }), 200

    except Exception as e:
        return jsonify({"status": "critical_error", "message": str(e)}), 200
    finally:
        con.close()