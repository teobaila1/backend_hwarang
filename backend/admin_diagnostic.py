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

    try:
        cur = con.cursor()

        # 1. CEREM LISTA TUTUROR COLOANELOR DIN TABELUL 'copii'
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'copii';
        """)
        columns = cur.fetchall()

        # Le transformăm într-o listă ușor de citit
        lista_coloane = [f"{col[0]} ({col[1]})" for col in columns]

        return jsonify({
            "status": "success",
            "mesaj": "Iata structura reala a tabelului COPII",
            "coloane_gasite": lista_coloane
        }), 200

    except Exception as e:
        return jsonify({"status": "critical_error", "message": str(e)}), 500
    finally:
        con.close()