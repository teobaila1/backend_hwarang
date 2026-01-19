import uuid
import re
import json
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from ..accounts.decorators import token_required

parinti_bp = Blueprint("parinti", __name__)


def _normalize_name(s):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _new_claim_code():
    return uuid.uuid4().hex[:8].upper()


def _get_or_create_group_id(cur, group_name):
    """Helper pentru a găsi ID-ul grupei."""
    if not group_name: return None
    g_norm = _normalize_name(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
    row = cur.fetchone()
    if row: return row['id']

    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
    return cur.fetchone()['id']


# --- CREARE PLACEHOLDER (De către Antrenor/Admin) ---
@parinti_bp.post("/api/parinti/placeholder")
@token_required
def create_parent_placeholder():
    data = request.get_json(silent=True) or {}
    nume = _normalize_name(data.get("nume"))

    if not nume:
        return jsonify({"status": "error", "message": "Numele părintelui este obligatoriu."}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        claim_code = _new_claim_code()
        dummy_email = f"placeholder_{claim_code}@hwarang.temp"

        # 1. Inserăm în UTILIZATORI
        cur.execute("""
            INSERT INTO utilizatori (
                username, nume_complet, email, parola, rol, 
                is_placeholder, claim_code, copii
            )
            VALUES (%s, %s, %s, 'NO_LOGIN_ACCOUNT', 'Parinte', 1, %s, '[]')
            RETURNING id
        """, (nume, nume, dummy_email, claim_code))

        parent_id = cur.fetchone()['id']

        # 2. Inserăm în ROLURI (Critic pentru noua structură!)
        cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, 'Parinte')", (parent_id,))

        con.commit()
        return jsonify({"status": "success", "id": parent_id, "claim_code": claim_code}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- REVENDICARE CONT (De către Părinte) ---
@parinti_bp.patch("/api/parinti/claim")
def claim_parent_account():
    data = request.get_json(silent=True) or {}

    # Date identificare
    nume = _normalize_name(data.get("nume"))
    claim_code = (data.get("claim_code") or "").strip().upper() or None

    # Date noi
    email = (data.get("email") or "").strip() or None
    parola_hash = data.get("parola_hash")
    copii_noi = data.get("copii")  # Listă de obiecte copii
    telefon = data.get("telefon")
    adresa = data.get("adresa")

    if not nume:
        return jsonify({"status": "error", "message": "Numele este obligatoriu."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Găsim contul placeholder
        row = None
        if claim_code:
            cur.execute(
                "SELECT id FROM utilizatori WHERE claim_code = %s AND is_placeholder = 1",
                (claim_code,)
            )
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Cod invalid sau deja revendicat."}), 404
        else:
            cur.execute(
                "SELECT id FROM utilizatori WHERE is_placeholder = 1 AND LOWER(username) = LOWER(%s)",
                (nume,)
            )
            rows = cur.fetchall()
            if not rows:
                return jsonify({"status": "error", "message": "Nu există cont de revendicat pe acest nume."}), 404
            if len(rows) > 1:
                return jsonify({"status": "error",
                                "message": "Există mai mulți părinți cu acest nume. Cere codul de la antrenor."}), 409
            row = rows[0]

        parent_id = row["id"]

        # 2. Actualizăm datele Părintelui
        fields, values = [], []
        if email:
            fields.append("email = %s")
            values.append(email)
        if parola_hash:
            fields.append("parola = %s")
            values.append(parola_hash)
        if telefon:
            fields.append("telefon = %s")
            values.append(telefon)
        if adresa:
            fields.append("adresa = %s")
            values.append(adresa)

        # Dezactivăm modul placeholder
        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")

        # Scriem și JSON-ul vechi ca backup (opțional, dar bun pentru compatibilitate)
        if copii_noi:
            fields.append("copii = %s")
            values.append(json.dumps(copii_noi))

        if fields:
            values.append(parent_id)
            cur.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", tuple(values))

        # 3. INSERT COPII ÎN TABELELE NOI (Partea Critică)
        if copii_noi and isinstance(copii_noi, list):
            for copil in copii_noi:
                c_nume = _normalize_name(copil.get("nume"))
                c_grupa = _normalize_name(copil.get("grupa"))
                c_gen = copil.get("gen")
                # Vârsta vine de obicei ca număr, nu avem data nașterii exactă la claim simplu
                # Putem lăsa data_nasterii NULL

                if c_nume:
                    c_id = uuid.uuid4().hex

                    # Inserăm în tabelul COPII
                    cur.execute("""
                        INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, added_by_trainer)
                        VALUES (%s, %s, %s, %s, %s, FALSE)
                    """, (c_id, parent_id, c_nume, c_gen, c_grupa))

                    # Legăm de Grupă (sportivi_pe_grupe)
                    if c_grupa:
                        gid = _get_or_create_group_id(cur, c_grupa)
                        if gid:
                            cur.execute("""
                                INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil)
                                VALUES (%s, %s)
                            """, (gid, c_id))

        con.commit()
        return jsonify({"status": "success", "id": parent_id, "message": "Cont activat cu succes!"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500