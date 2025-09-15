# backend/users/parinti.py
import uuid, re
from flask import Blueprint, request, jsonify
from backend.config import get_conn

parinti_bp = Blueprint("parinti", __name__)

def _normalize_name(s):
    s = (s or "").strip()
    # spații multiple -> spațiu simplu; primele litere mari
    s = re.sub(r"\s+", " ", s)
    return s

def _new_claim_code():
    # cod scurt, lizibil (8 chars)
    return uuid.uuid4().hex[:8].upper()

@parinti_bp.post("/api/parinti/placeholder")
def create_parent_placeholder():
    data = request.get_json(silent=True) or {}
    nume = _normalize_name(data.get("nume"))
    if not nume:
        return jsonify({"status": "error", "message": "Numele părintelui este obligatoriu."}), 400

    con = get_conn()
    try:
        claim_code = _new_claim_code()

        # INSERT dinamic, compatibil cu schema curentă
        cols = ["rol", "username", "email", "is_placeholder", "claim_code", "created_by_trainer", "copii", "grupe"]
        vals = ["parinte", nume, None, 1, claim_code, 1, "[]", ""]

        # dacă ai coloana nume_complet, o setăm
        cur_cols = {r[1] for r in con.execute("PRAGMA table_info(utilizatori)").fetchall()}
        if "nume_complet" in cur_cols:
            cols.append("nume_complet"); vals.append(nume)

        placeholders = ", ".join(["?"] * len(cols))
        sql = f"INSERT INTO utilizatori ({', '.join(cols)}) VALUES ({placeholders})"
        cur = con.execute(sql, tuple(vals))

        parent_id = cur.lastrowid
        con.commit()
        return jsonify({"status": "success", "id": parent_id, "claim_code": claim_code}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@parinti_bp.patch("/api/parinti/claim")
def claim_parent_account():
    data = request.get_json(silent=True) or {}
    nume  = _normalize_name(data.get("nume"))
    email = (data.get("email") or "").strip() or None
    parola_hash = data.get("parola_hash")
    claim_code  = (data.get("claim_code") or "").strip().upper() or None

    if not nume:
        return jsonify({"status": "error", "message": "Numele este obligatoriu."}), 400

    con = get_conn()
    try:
        row = None
        if claim_code:
            row = con.execute(
                "SELECT * FROM utilizatori WHERE claim_code = ? AND is_placeholder = 1",
                (claim_code,)
            ).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Cod invalid sau deja revendicat."}), 404
        else:
            # match pe username (nu pe o coloană 'nume' inexistentă)
            rows = con.execute(
                "SELECT * FROM utilizatori WHERE is_placeholder = 1 AND LOWER(username) = LOWER(?)",
                (nume,)
            ).fetchall()
            if not rows:
                return jsonify({"status": "error", "message": "Nu există placeholder pe acest nume."}), 404
            if len(rows) > 1:
                return jsonify({"status": "error", "message": "Există mai mulți părinți cu acest nume. Cere un claim_code de la antrenor."}), 409
            row = rows[0]

        parent_id = row["id"]

        fields, values = [], []
        if email is not None:
            fields.append("email = ?");  values.append(email)
        if parola_hash:
            fields.append("parola = ?"); values.append(parola_hash)
        # alte câmpuri opționale
        for k in ("telefon", "adresa"):
            if k in data:
                fields.append(f"{k} = ?")
                values.append((data.get(k) or "").strip() or None)

        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")

        if not fields:
            return jsonify({"status": "error", "message": "Nu ai trimis date noi de completat."}), 400

        values.append(parent_id)
        con.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = ?", values)
        con.commit()
        return jsonify({"status": "success", "id": parent_id}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500