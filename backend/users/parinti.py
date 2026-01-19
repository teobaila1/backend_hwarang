import uuid
import re
import json
import datetime
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


# --- 1. CREARE PLACEHOLDER (Admin/Antrenor) ---
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

        # Insert User
        cur.execute("""
            INSERT INTO utilizatori (
                username, nume_complet, email, parola, rol, 
                is_placeholder, claim_code, copii
            )
            VALUES (%s, %s, %s, 'NO_LOGIN_ACCOUNT', 'Parinte', 1, %s, '[]')
            RETURNING id
        """, (nume, nume, dummy_email, claim_code))

        parent_id = cur.fetchone()['id']

        # Insert Rol
        cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, 'Parinte')", (parent_id,))

        con.commit()
        return jsonify({"status": "success", "id": parent_id, "claim_code": claim_code}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 2. REVENDICARE CONT (Părinte neautentificat) ---
@parinti_bp.patch("/api/parinti/claim")
def claim_parent_account():
    data = request.get_json(silent=True) or {}
    nume = _normalize_name(data.get("nume"))
    claim_code = (data.get("claim_code") or "").strip().upper() or None
    email = (data.get("email") or "").strip() or None
    parola_hash = data.get("parola_hash")
    copii_noi = data.get("copii")
    telefon = data.get("telefon")
    adresa = data.get("adresa")

    if not nume:
        return jsonify({"status": "error", "message": "Numele este obligatoriu."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # Găsim contul placeholder
        row = None
        if claim_code:
            cur.execute("SELECT id FROM utilizatori WHERE claim_code = %s AND is_placeholder = 1", (claim_code,))
            row = cur.fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Cod invalid sau deja revendicat."}), 404
        else:
            cur.execute("SELECT id FROM utilizatori WHERE is_placeholder = 1 AND LOWER(username) = LOWER(%s)", (nume,))
            rows = cur.fetchall()
            if not rows:
                return jsonify({"status": "error", "message": "Nu există cont de revendicat pe acest nume."}), 404
            if len(rows) > 1:
                return jsonify({"status": "error", "message": "Sunt mai mulți părinți cu acest nume. Cere codul."}), 409
            row = rows[0]

        parent_id = row["id"]

        # Update date Părinte
        fields, values = [], []
        if email: fields.append("email = %s"); values.append(email)
        if parola_hash: fields.append("parola = %s"); values.append(parola_hash)
        if telefon: fields.append("telefon = %s"); values.append(telefon)
        if adresa: fields.append("adresa = %s"); values.append(adresa)

        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")

        if copii_noi:
            fields.append("copii = %s")  # Backup JSON
            values.append(json.dumps(copii_noi))

        values.append(parent_id)
        cur.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", tuple(values))

        # Migrare copii în tabel SQL
        if copii_noi and isinstance(copii_noi, list):
            for copil in copii_noi:
                c_nume = _normalize_name(copil.get("nume"))
                c_grupa = _normalize_name(copil.get("grupa"))
                c_gen = copil.get("gen")

                if c_nume:
                    c_id = uuid.uuid4().hex
                    cur.execute("""
                        INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, added_by_trainer)
                        VALUES (%s, %s, %s, %s, %s, FALSE)
                    """, (c_id, parent_id, c_nume, c_gen, c_grupa))

                    if c_grupa:
                        gid = _get_or_create_group_id(cur, c_grupa)
                        if gid:
                            cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                        (gid, c_id))

        con.commit()
        return jsonify({"status": "success", "id": parent_id, "message": "Cont activat!"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 3. COPIII MEI (Gestionează copiii din dashboard Părinte) ---
# Aceasta este secțiunea care lipsea!

@parinti_bp.get("/api/copiii_mei")
@token_required
def get_my_children():
    """Returnează lista copiilor pentru părintele logat."""
    user_id = request.user_id  # Vine din decorator
    con = get_conn()
    try:
        cur = con.cursor()
        # Citim din tabelul nou 'copii'
        try:
            cur.execute("SELECT id, nume, gen, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))
        except:
            con.rollback()
            # Fallback (dacă nu ai apucat să migrezi coloana grupa_text)
            cur.execute("SELECT id, nume, gen, data_nasterii FROM copii WHERE id_parinte = %s", (user_id,))

        rows = cur.fetchall()
        children = []
        for r in rows:
            dob = str(r.get('data_nasterii') or "")
            grp = r.get('grupa_text') or ""
            children.append({
                "id": r['id'],
                "nume": r['nume'],
                "gen": r['gen'],
                "grupa": grp,
                "varsta": dob  # Frontend-ul se așteaptă la varsta, trimitem data nașterii ca string
            })

        return jsonify(children), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@parinti_bp.post("/api/copiii_mei")
@token_required
def add_my_child():
    """Părintele adaugă un copil nou."""
    user_id = request.user_id
    data = request.get_json(silent=True) or {}

    nume = _normalize_name(data.get("nume"))
    grupa = _normalize_name(data.get("grupa"))
    gen = data.get("gen")

    # Frontend-ul trimite "varsta" (int) din formular.
    # Noi avem "data_nasterii" (DATE).
    # Facem o aproximare ca să nu crape (ex: 1 Ianuarie a anului calculat)
    varsta_input = data.get("varsta")
    data_nasterii_calc = None

    if varsta_input and str(varsta_input).isdigit():
        an_curent = datetime.datetime.now().year
        an_nastere = an_curent - int(varsta_input)
        data_nasterii_calc = f"{an_nastere}-01-01"

    if not nume:
        return jsonify({"status": "error", "message": "Numele copilului este obligatoriu"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        new_id = uuid.uuid4().hex

        # 1. Insert în COPII
        cur.execute("""
            INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
        """, (new_id, user_id, nume, gen, grupa, data_nasterii_calc))

        # 2. Insert în SPORTIVI_PE_GRUPE (pentru Antrenor)
        if grupa:
            gid = _get_or_create_group_id(cur, grupa)
            if gid:
                cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)", (gid, new_id))

        con.commit()
        return jsonify({"status": "success", "message": "Copil adăugat!"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@parinti_bp.delete("/api/copiii_mei/<child_id>")
@token_required
def delete_my_child(child_id):
    """Părintele șterge un copil."""
    user_id = request.user_id
    con = get_conn()
    try:
        cur = con.cursor()

        # Verificăm că e copilul lui
        cur.execute("DELETE FROM copii WHERE id = %s AND id_parinte = %s", (child_id, user_id))

        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Copilul nu a fost găsit sau nu îți aparține."}), 404

        con.commit()
        return jsonify({"status": "success", "message": "Copil șters."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500