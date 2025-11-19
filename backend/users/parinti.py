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


def _get_columns(con, table_name: str):
    """
    Returnează setul de coloane pentru un tabel, funcționând atât pe PostgreSQL,
    cât și pe SQLite.
    """
    cols = set()

    # Încercăm întâi varianta PostgreSQL (information_schema)
    try:
        rows = con.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,)).fetchall()
        if rows:
            return {r[0] for r in rows}
    except Exception:
        pass

    # Fallback: SQLite PRAGMA, dacă suntem pe SQLite
    try:
        info = con.execute(f"PRAGMA table_info({table_name})").fetchall()
        # format: (cid, name, type, notnull, dflt_value, pk)
        cols = {r[1] for r in info}
    except Exception:
        cols = set()

    return cols


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
        cur_cols = _get_columns(con, "utilizatori")
        if "nume_complet" in cur_cols:
            cols.append("nume_complet")
            vals.append(nume)

        placeholders = ", ".join(["?"] * len(cols))  # `?` va fi convertit în `%s` de wrapper-ul din config.py
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
    nume = _normalize_name(data.get("nume"))
    email = (data.get("email") or "").strip() or None
    parola_hash = data.get("parola_hash")
    claim_code = (data.get("claim_code") or "").strip().upper() or None

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
            # match pe username (nu pe o coloană 'nume' inexistentă)
            rows = con.execute(
                "SELECT * FROM utilizatori WHERE is_placeholder = 1 AND LOWER(username) = LOWER(%s)",
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
            fields.append("email = %s")
            values.append(email)
        if parola_hash:
            fields.append("parola = %s")
            values.append(parola_hash)
        # alte câmpuri opționale
        for k in ("telefon", "adresa"):
            if k in data:
                fields.append(f"{k} = %s")
                values.append((data.get(k) or "").strip() or None)

        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")

        if not fields:
            return jsonify({"status": "error", "message": "Nu ai trimis date noi de completat."}), 400

        values.append(parent_id)
        con.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", values)
        con.commit()
        return jsonify({"status": "success", "id": parent_id}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
