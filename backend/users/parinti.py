import uuid
import re
import json
import datetime
from datetime import date
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required

parinti_bp = Blueprint("parinti", __name__)


# --- HELPERS ---

def _normalize_name(s):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


# Repară numele grupei (Ex: "1" -> "Grupa 1")
def _normalize_group_name(g):
    if not g: return ""
    g = str(g).strip()

    # 1. Dacă e doar număr (ex: "1", "2"), îl transformăm în "Grupa 1"
    if g.isdigit():
        return f"Grupa {g}"

    # 2. Dacă scrie "gr 1" sau "gr.1", corectăm în "Grupa 1"
    if g.lower().startswith("gr") and any(c.isdigit() for c in g):
        nums = re.findall(r'\d+', g)
        if nums:
            return f"Grupa {nums[0]}"

    # 3. Altfel, lăsăm numele așa cum e
    return _normalize_name(g)


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    g_norm = _normalize_group_name(group_name)

    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
    row = cur.fetchone()
    if row: return row['id']

    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
    return cur.fetchone()['id']


def _new_claim_code():
    return uuid.uuid4().hex[:8].upper()


# --- 1. CREARE PLACEHOLDER (Pentru Antrenori) ---
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


# --- 2. REVENDICARE CONT (Claim) ---
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

        # Migrare copii la claim
        if copii_noi and isinstance(copii_noi, list):
            for copil in copii_noi:
                c_nume = _normalize_name(copil.get("nume"))
                c_grupa = _normalize_name(copil.get("grupa"))
                c_gen = copil.get("gen")
                # Fix pentru dată la claim (dacă există)
                c_data = copil.get("data_nasterii")

                if c_nume:
                    c_id = uuid.uuid4().hex
                    cur.execute("""
                        INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                    """, (c_id, parent_id, c_nume, c_gen, c_grupa, c_data))
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


# --- RUTELE PENTRU COPIII MEI (ACTUALIZATE) ---

@parinti_bp.get("/api/copiii_mei")
@token_required
def get_my_children():
    user_id = request.user_id
    con = get_conn()
    try:
        cur = con.cursor()
        # Am adăugat data_nasterii în SELECT
        sql = "SELECT id, nume, gen, grupa_text, data_nasterii FROM copii WHERE id_parinte = %s ORDER BY nume ASC"
        cur.execute(sql, (user_id,))
        rows = cur.fetchall()

        children = []
        for r in rows:
            grp = r.get('grupa_text') or ""
            # Convertim data în string YYYY-MM-DD pentru frontend
            dn_str = str(r['data_nasterii']) if r['data_nasterii'] else ""

            children.append({
                "id": r['id'],
                "nume": r['nume'],
                "gen": r['gen'],
                "grupa": grp,
                "data_nasterii": dn_str  # Trimitem data exactă
            })

        return jsonify(children), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()


@parinti_bp.post("/api/copiii_mei")
@token_required
def add_my_child():
    user_id = request.user_id
    data = request.get_json(silent=True) or {}

    # 1. Numele vine acum complet din Frontend (Nume + Prenume)
    nume_copil_input = _normalize_name(data.get("nume"))

    if not nume_copil_input:
        return jsonify({"status": "error", "message": "Numele este obligatoriu"}), 400

    raw_grupa = data.get("grupa")
    grupa = _normalize_group_name(raw_grupa)
    gen = data.get("gen")

    # 2. VALIDARE DATĂ STRICTĂ
    data_nasterii_input = data.get("data_nasterii")

    # Dacă data e goală sau invalidă, punem NULL, nu lăsăm string gol
    if not data_nasterii_input or len(str(data_nasterii_input).strip()) < 10:
        data_nasterii_input = None
    else:
        # Încercăm să vedem dacă e format corect YYYY-MM-DD
        try:
            # Asta va arunca eroare dacă data e "2023" sau "test"
            datetime.date.fromisoformat(str(data_nasterii_input))
        except ValueError:
            return jsonify(
                {"status": "error", "message": "Formatul datei de naștere este invalid. Folosiți calendarul."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # Verificăm duplicate
        cur.execute("SELECT id FROM copii WHERE id_parinte = %s AND LOWER(nume) = LOWER(%s)",
                    (user_id, nume_copil_input))
        if cur.fetchone():
            return jsonify({"status": "error", "message": "Acest copil există deja în listă."}), 409

        new_id = uuid.uuid4().hex

        # 3. Inserăm
        cur.execute("""
            INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
        """, (new_id, user_id, nume_copil_input, gen, grupa, data_nasterii_input))

        # 4. Legătură cu Grupa
        if grupa:
            gid = _get_or_create_group_id(cur, grupa)
            if gid:
                cur.execute("""
                    INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) 
                    VALUES (%s, %s)
                    ON CONFLICT (id_grupa, id_sportiv_copil) DO NOTHING
                """, (gid, new_id))

        con.commit()

        msg = f"Copil adăugat: {nume_copil_input}"
        return jsonify({"status": "success", "message": msg}), 200

    except Exception as e:
        con.rollback()
        print(f"[SQL ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()


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
    finally:
        if con: con.close()