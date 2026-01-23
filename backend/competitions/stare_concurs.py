from flask import Blueprint, jsonify
from ..accounts.decorators import token_required, admin_required
from ..config import get_conn
import urllib.parse

stare_concurs_bp = Blueprint('stare_concurs', __name__)


@stare_concurs_bp.post('/api/concursuri/toggle_status/<nume>')
@token_required
@admin_required
def toggle_status(nume: str):
    decoded_name = (urllib.parse.unquote(nume) or "").strip()

    try:
        con = get_conn()
        # 1. Verificăm starea actuală
        row = con.execute("SELECT inscrieri_deschise FROM concursuri WHERE LOWER(nume) = LOWER(%s)",
                          (decoded_name,)).fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Concursul nu există"}), 404

        # 2. Inversăm starea (Dacă era True devine False)
        # Folosim 'inscrieri_deschise' dacă există, altfel presupunem True
        current_status = row['inscrieri_deschise'] if 'inscrieri_deschise' in row else True
        new_status = not current_status

        con.execute("UPDATE concursuri SET inscrieri_deschise = %s WHERE LOWER(nume) = LOWER(%s)",
                    (new_status, decoded_name))
        con.commit()

        msg = "DESCHISE" if new_status else "ÎNCHISE"
        return jsonify({"status": "success", "message": f"Înscrierile sunt acum {msg}."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500