# backend/users/parinti.py
import uuid
import re
import json
from flask import Blueprint, request, jsonify
from backend.config import get_conn

parinti_bp = Blueprint("parinti", __name__)


def _normalize_name(s):
    s = (s or "").strip()
    # spații multiple -> spațiu simplu
    s = re.sub(r"\s+", " ", s)
    return s


def _new_claim_code():
    # cod scurt, lizibil (8 chars)
    return uuid.uuid4().hex[:8].upper()


# Endpoint folosit dacă vrei să creezi doar un părinte gol, fără copii (opțional)
# --- SECURIZAT: Doar un utilizator logat (Antrenor) poate genera placeholder ---
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

        # Generăm același tip de email dummy ca în elevi.py
        dummy_email = f"-_{claim_code}"

        cur = con.execute("""
            INSERT INTO utilizatori (
                rol, 
                username, 
                nume_complet, 
                email, 
                is_placeholder, 
                claim_code, 
                created_by_trainer, 
                copii, 
                parola
            )
            VALUES (
                'parinte', 
                %s, 
                %s, 
                %s,  -- dummy email
                1, 
                %s, 
                1, 
                '[]', 
                'NO_LOGIN_ACCOUNT' -- dummy password
            )
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


# --- LOGICA PRINCIPALĂ DE ACTIVARE CONT ---
@parinti_bp.patch("/api/parinti/claim")
def claim_parent_account():
    data = request.get_json(silent=True) or {}

    # 1. Identificăm contul
    nume = _normalize_name(data.get("nume"))
    claim_code = (data.get("claim_code") or "").strip().upper() or None

    # 2. Datele reale ale părintelui
    email = (data.get("email") or "").strip() or None
    parola_hash = data.get("parola_hash")

    # 3. Lista de copii (dacă părintele a completat-o în formular)
    copii_noi = data.get("copii")

    if not nume:
        return jsonify({"status": "error", "message": "Numele este obligatoriu."}), 400

    con = get_conn()
    try:
        row = None
        # Căutăm contul placeholder
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

        # Construim lista de actualizări SQL
        fields, values = [], []

        if email:
            fields.append("email = %s")
            values.append(email)
        if parola_hash:
            fields.append("parola = %s")
            values.append(parola_hash)

        # --- SUPRASCRIERE COPII ---
        # Dacă frontend-ul trimite o listă de copii (chiar și goală), suprascriem ce era înainte.
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

            fields.append("copii = %s")
            values.append(json.dumps(lista_procesata, ensure_ascii=False))
        # --------------------------

        for k in ("telefon", "adresa"):
            if k in data:
                fields.append(f"{k} = %s")
                values.append((data.get(k) or "").strip() or None)

        # Transformăm contul în unul real
        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")

        if not fields:
            return jsonify({"status": "error", "message": "Nu ai trimis date noi."}), 400

        values.append(parent_id)
        con.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", values)
        con.commit()

        return jsonify({
            "status": "success",
            "id": parent_id,
            "message": "Cont activat cu succes!"
        }), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500