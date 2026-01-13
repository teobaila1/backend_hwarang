import uuid
import re
import json
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from ..auth.decorators import token_required

parinti_bp = Blueprint("parinti", __name__)


def _normalize_name(s):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _new_claim_code():
    return uuid.uuid4().hex[:8].upper()


# --- SECURIZAT: Generare placeholder ---
@parinti_bp.post("/api/parinti/placeholder")
@token_required
def create_parent_placeholder():
    data = request.get_json(silent=True) or {}
    nume = _normalize_name(data.get("nume"))
    if not nume:
        return jsonify({"status": "error", "message": "Numele părintelui este obligatoriu."}), 400

    con = get_conn()
    try:
        claim_code = _new_claim_code()
        dummy_email = f"placeholder_{claim_code}@hwarang.temp"

        # --- AICI: Forțăm rolul 'Parinte' ---
        cur = con.execute("""
            INSERT INTO utilizatori (
                rol, 
                username, 
                nume_complet, 
                email, 
                is_placeholder, 
                claim_code, 
                copii, 
                parola
            )
            VALUES ('Parinte', %s, %s, %s, 1, %s, '[]', 'NO_LOGIN_ACCOUNT')
            RETURNING id
        """, (nume, nume, dummy_email, claim_code))

        try:
            new_row = cur.fetchone()
            parent_id = new_row['id'] if new_row else cur.lastrowid
        except:
            parent_id = cur.lastrowid

        con.commit()
        return jsonify({"status": "success", "id": parent_id, "claim_code": claim_code}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- PUBLIC: Revendicare cont (rămâne neschimbat, dar îl pun pentru completitudine) ---
@parinti_bp.patch("/api/parinti/claim")
def claim_parent_account():
    data = request.get_json(silent=True) or {}
    nume = _normalize_name(data.get("nume"))
    claim_code = (data.get("claim_code") or "").strip().upper() or None
    email = (data.get("email") or "").strip() or None
    parola_hash = data.get("parola_hash")
    copii_noi = data.get("copii")

    if not nume:
        return jsonify({"status": "error", "message": "Numele este obligatoriu."}), 400

    con = get_conn()
    try:
        row = None
        if claim_code:
            row = con.execute(
                "SELECT * FROM utilizatori WHERE claim_code = %s AND is_placeholder = 1",
                (claim_code,)
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Cod invalid sau deja revendicat."}), 404
        else:
            rows = con.execute(
                "SELECT * FROM utilizatori WHERE is_placeholder = 1 AND LOWER(username) = LOWER(%s)",
                (nume,)
            ).fetchall()
            if not rows:
                return jsonify({"status": "error", "message": "Nu există cont de revendicat pe acest nume."}), 404
            if len(rows) > 1:
                return jsonify({"status": "error",
                                "message": "Sunt mai mulți părinți cu acest nume. Cere codul de la antrenor."}), 409
            row = rows[0]

        parent_id = row["id"]
        fields, values = [], []

        if email:
            fields.append("email = %s");
            values.append(email)
        if parola_hash:
            fields.append("parola = %s");
            values.append(parola_hash)

        if copii_noi is not None and isinstance(copii_noi, list):
            lista_procesata = []
            for copil in copii_noi:
                if isinstance(copil, dict):
                    c_nou = {
                        "id": copil.get("id") or uuid.uuid4().hex,
                        "nume": copil.get("nume", "").strip(),
                        "varsta": copil.get("varsta"),
                        "gen": copil.get("gen"),
                        "grupa": copil.get("grupa", "")
                    }
                    lista_procesata.append(c_nou)
            fields.append("copii = %s");
            values.append(json.dumps(lista_procesata, ensure_ascii=False))

        for k in ("telefon", "adresa"):
            if k in data:
                fields.append(f"{k} = %s");
                values.append((data.get(k) or "").strip() or None)

        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")

        if not fields:
            return jsonify({"status": "error", "message": "Nu ai trimis date noi."}), 400

        values.append(parent_id)
        con.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", values)
        con.commit()
        return jsonify({"status": "success", "id": parent_id, "message": "Cont activat cu succes!"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500