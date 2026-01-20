import uuid
import re
import json
import datetime
from datetime import date
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
    if not group_name: return None
    g_norm = _normalize_name(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
    return cur.fetchone()['id']


def _calc_age(dob):
    """Calculează vârsta numerică."""
    if not dob: return ""
    try:
        today = date.today()
        if isinstance(dob, str):
            dob = date.fromisoformat(dob)
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return ""


# --- 1. CREARE PLACEHOLDER ---
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

        cur.execute("""
            INSERT INTO utilizatori (
                username, nume_complet, email, parola, rol, 
                is_placeholder, claim_code, copii
            )
            VALUES (%s, %s, %s, 'NO_LOGIN_ACCOUNT', 'Parinte', 1, %s, '[]')
            RETURNING id
        """, (nume, nume, dummy_email, claim_code))

        parent_id = cur.fetchone()['id']
        cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, 'Parinte')", (parent_id,))
        con.commit()
        return jsonify({"status": "success", "id": parent_id, "claim_code": claim_code}), 201
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 2. REVENDICARE CONT ---
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
        if claim_code:
            cur.execute("SELECT id FROM utilizatori WHERE claim_code = %s AND is_placeholder = 1", (claim_code,))
            row = cur.fetchone()
            if not row: return jsonify({"status": "error", "message": "Cod invalid."}), 404
        else:
            cur.execute("SELECT id FROM utilizatori WHERE is_placeholder = 1 AND LOWER(username) = LOWER(%s)", (nume,))
            rows = cur.fetchall()
            if not rows: return jsonify({"status": "error", "message": "Nu există cont."}), 404
            row = rows[0]

        parent_id = row["id"]
        fields, values = [], []
        if email: fields.append("email = %s"); values.append(email)
        if parola_hash: fields.append("parola = %s"); values.append(parola_hash)
        if telefon: fields.append("telefon = %s"); values.append(telefon)
        if adresa: fields.append("adresa = %s"); values.append(adresa)

        fields.append("is_placeholder = 0")
        fields.append("claim_code = NULL")
        if copii_noi:
            fields.append("copii = %s")
            values.append(json.dumps(copii_noi))

        values.append(parent_id)
        cur.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", tuple(values))

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


import uuid
import re
import json
import datetime
from datetime import date
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
    if not group_name: return None
    g_norm = _normalize_name(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
    return cur.fetchone()['id']


def _calc_age(dob):
    """Calculează vârsta numerică."""
    if not dob: return ""
    try:
        today = date.today()
        if isinstance(dob, str):
            dob = date.fromisoformat(dob)
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return ""


# --- RUTA DE PROBLEMĂ ---
@parinti_bp.get("/api/copiii_mei")
@token_required
def get_my_children():
    user_id = request.user_id

    # --- DEBUGGING START ---
    print(f"\n[DEBUG COPII] User ID Logat: {user_id}")
    # -----------------------

    con = get_conn()
    try:
        cur = con.cursor()

        # Facem query-ul
        sql = "SELECT id, nume, gen, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s"
        cur.execute(sql, (user_id,))
        rows = cur.fetchall()

        # --- DEBUGGING REZULTATE ---
        print(f"[DEBUG COPII] Query SQL: {sql}")
        print(f"[DEBUG COPII] Copii gasiti in DB: {len(rows)}")
        if len(rows) > 0:
            print(f"[DEBUG COPII] Exemplu copil gasit: {rows[0]['nume']}")
        else:
            print(
                f"[DEBUG COPII] LISTA E GOALĂ! Verifică dacă user_id din token corespunde cu id_parinte din tabelul copii.")
        # ---------------------------

        children = []
        for r in rows:
            varsta_num = _calc_age(r.get('data_nasterii'))
            grp = r.get('grupa_text') or ""
            children.append({
                "id": r['id'],
                "nume": r['nume'],
                "gen": r['gen'],
                "grupa": grp,
                "varsta": str(varsta_num)
            })

        return jsonify(children), 200
    except Exception as e:
        print(f"[DEBUG ERROR] {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()


@parinti_bp.post("/api/copiii_mei")
@token_required
def add_my_child():
    user_id = request.user_id
    data = request.get_json(silent=True) or {}

    nume = _normalize_name(data.get("nume"))
    grupa = _normalize_name(data.get("grupa"))
    gen = data.get("gen")

    varsta_input = data.get("varsta")
    data_nasterii_calc = None
    if varsta_input and str(varsta_input).isdigit():
        an_curent = datetime.datetime.now().year
        an_nastere = an_curent - int(varsta_input)
        data_nasterii_calc = f"{an_nastere}-01-01"

    if not nume:
        return jsonify({"status": "error", "message": "Numele este obligatoriu"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        new_id = uuid.uuid4().hex

        print(f"[DEBUG ADD] Adaug copil pentru parintele: {user_id}")

        cur.execute("""
            INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
        """, (new_id, user_id, nume, gen, grupa, data_nasterii_calc))

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
    user_id = request.user_id
    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM copii WHERE id = %s AND id_parinte = %s", (child_id, user_id))
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Eroare la ștergere."}), 404
        con.commit()
        return jsonify({"status": "success", "message": "Copil șters."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ... Restul funcțiilor (placeholder, claim) rămân neschimbate, le poți păstra pe cele din fișierul tău anterior ...
# Adaugă aici funcțiile create_parent_placeholder și claim_parent_account din fișierul tău vechi pentru a fi complet.
# (Din motive de spațiu le-am omis, dar ele trebuie să fie în fișier pentru a nu avea erori la import)
# --- INSERT REST OF FUNCTIONS HERE ---
# Copiază create_parent_placeholder și claim_parent_account din fișierul anterior.