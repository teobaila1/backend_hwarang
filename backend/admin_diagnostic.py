from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

admin_diagnostic_bp = Blueprint('admin_diagnostic', __name__)


@admin_diagnostic_bp.get("/api/admin/diagnostic-date")
@token_required
def get_diagnostic_report():
    # Verificare admin
    if getattr(request, 'user_role', '') != 'admin':
        return jsonify({"status": "error", "message": "Acces interzis!"}), 403

    con = get_conn()
    try:
        # PASUL 1: Resetăm orice tranzacție blocată anterior
        con.rollback()

        cur = con.cursor()

        # PASUL 2: Cerem 0 rânduri din tabelul copii.
        # Asta nu încarcă date, dar ne dă numele coloanelor.
        cur.execute("SELECT * FROM copii LIMIT 0")

        # Extragem numele coloanelor din descrierea cursorului
        nume_coloane = [desc[0] for desc in cur.description]

        return jsonify({
            "status": "success",
            "mesaj": "Am reusit! Iata coloanele din tabelul COPII:",
            "coloane_gasite": nume_coloane
        }), 200

    except Exception as e:
        # Returnăm eroarea completă (Tip + Mesaj) ca să nu mai primim doar '0'
        return jsonify({
            "status": "critical_error",
            "message": f"{type(e).__name__}: {str(e)}"
        }), 500
    finally:
        con.close()