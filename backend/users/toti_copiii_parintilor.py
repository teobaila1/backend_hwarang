import json
import re
import uuid
from datetime import date
from flask import Blueprint, jsonify, request
from ..accounts.decorators import admin_required, token_required
from ..config import get_conn

toti_copiii_parintilor_bp = Blueprint('copiii_parintilor', __name__)


def _normalize_name(s):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    gn = _normalize_name(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (gn,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (gn,))
    return cur.fetchone()['id']


def _calc_age(dob):
    """Calculează vârsta pe baza datei nașterii."""
    if not dob:
        return ""
    try:
        today = date.today()
        # dob poate veni ca string sau ca obiect date
        if isinstance(dob, str):
            dob = date.fromisoformat(dob)
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return ""


# --- LISTARE TOȚI COPIII (Admin) ---
@toti_copiii_parintilor_bp.get("/api/toti_copiii")
@token_required
@admin_required
def toti_copiii():
    try:
        con = get_conn()
        cur = con.cursor()
        # Selectam si data_nasterii
        cur.execute("""
            SELECT c.id, c.nume, c.data_nasterii, c.gen, c.grupa_text,
                   u.id as pid, u.username, u.email, u.nume_complet
            FROM copii c
            JOIN utilizatori u ON c.id_parinte = u.id
            ORDER BY u.username, c.nume
        """)
        rows = cur.fetchall()

        map_parinti = {}
        for r in rows:
            pid = r['pid']
            if pid not in map_parinti:
                map_parinti[pid] = {
                    "parinte": {
                        "id": pid,
                        "username": r['username'],
                        "email": r['email'],
                        "nume_complet": r['nume_complet']
                    },
                    "copii": []
                }

            # Calculăm vârsta pentru afișare în tabel
            varsta_calc = _calc_age(r['data_nasterii'])

            # Pregătim data pentru calendar (YYYY-MM-DD)
            dn_str = str(r['data_nasterii']) if r['data_nasterii'] else ""

            # Reparăm Genul (m -> M)
            gen_cap = (r['gen'] or "").capitalize()

            map_parinti[pid]["copii"].append({
                "id": r['id'],
                "nume": r['nume'],
                "varsta": str(varsta_calc),
                "data_nasterii": dn_str,  # <-- IMPORTANT pentru Editare
                "gen": gen_cap,  # <-- IMPORTANT pentru Select
                "grupa": r['grupa_text']
            })

        return jsonify({"status": "success", "date": list(map_parinti.values())}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ADĂUGARE COPIL (Admin pt Părinte) ---
@toti_copiii_parintilor_bp.post("/api/adauga_copil")
@token_required
@admin_required
def adauga_copil():
    data = request.get_json(silent=True) or {}
    target_username = data.get("parinte_username")
    nume = data.get("nume")
    grupa = data.get("grupa")
    gen = data.get("gen")
    data_nasterii = data.get("data_nasterii")  # YYYY-MM-DD

    if not target_username or not nume:
        return jsonify({"status": "error", "message": "Date incomplete"}), 400

    try:
        con = get_conn()
        cur = con.cursor()

        cur.execute("SELECT id FROM utilizatori WHERE username = %s", (target_username,))
        row = cur.fetchone()
        if not row: return jsonify({"status": "error", "message": "Părinte inexistent"}), 404
        pid = row['id']

        new_id = uuid.uuid4().hex

        cur.execute("""
            INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, data_nasterii, added_by_trainer)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (new_id, pid, nume, gen, grupa, data_nasterii))

        if grupa:
            gid = _get_or_create_group_id(cur, grupa)
            if gid:
                cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)", (gid, new_id))

        con.commit()
        return jsonify({"status": "success", "message": "Copil adăugat!"}), 200
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- EDITARE COPIL (Fix pentru Data Nașterii) ---
@toti_copiii_parintilor_bp.patch("/api/admin/copii/<child_id>")
@token_required
@admin_required
def admin_edit_child(child_id):
    data = request.get_json(silent=True) or {}
    nume = _normalize_name(data.get("nume"))
    grupa = _normalize_name(data.get("grupa"))
    gen = data.get("gen")
    data_nasterii = data.get("data_nasterii")  # <-- Primim data nouă

    try:
        con = get_conn()
        cur = con.cursor()

        # Update inclusiv data_nasterii
        fields = ["nume = %s", "gen = %s", "grupa_text = %s", "data_nasterii = %s"]
        values = [nume, gen, grupa, data_nasterii, child_id]

        cur.execute(f"UPDATE copii SET {', '.join(fields)} WHERE id = %s", tuple(values))

        # Update grupe
        cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_copil = %s", (child_id,))

        if grupa:
            gid = _get_or_create_group_id(cur, grupa)
            if gid:
                cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                            (gid, child_id))

        con.commit()
        return jsonify({"status": "success", "message": "Date copil actualizate."}), 200
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ȘTERGERE COPIL (Admin) ---
@toti_copiii_parintilor_bp.delete("/api/admin/copii/<child_id>")
@token_required
@admin_required
def admin_delete_child(child_id):
    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute("DELETE FROM copii WHERE id = %s", (child_id,))
        con.commit()
        return jsonify({"status": "success", "message": "Copil șters."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- RESTUL RUTELOR (DELETE/UPDATE PARINTE) RAMAN NESCHIMBATE ---
@toti_copiii_parintilor_bp.delete("/api/admin/parinte/<parent_username>")
@token_required
@admin_required
def admin_delete_parent(parent_username):
    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute("DELETE FROM utilizatori WHERE username=%s", (parent_username,))
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Utilizatorul nu există."}), 404
        con.commit()
        return jsonify({"status": "success", "message": "Părinte șters."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@toti_copiii_parintilor_bp.patch("/api/admin/parinte/<parent_username>")
@token_required
@admin_required
def admin_update_parent(parent_username):
    data = request.get_json(silent=True) or {}
    new_username = (data.get("new_username") or "").strip() or parent_username
    email = data.get("email")
    nume_complet = data.get("nume_complet")

    try:
        con = get_conn()
        cur = con.cursor()
        if new_username.lower() != parent_username.lower():
            cur.execute("SELECT 1 FROM utilizatori WHERE LOWER(username)=LOWER(%s)", (new_username,))
            if cur.fetchone():
                return jsonify({"status": "error", "message": "Username deja folosit."}), 409

        cur.execute("""
            UPDATE utilizatori 
            SET username=%s, email=%s, nume_complet=%s 
            WHERE username=%s
        """, (new_username, email, nume_complet, parent_username))

        con.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500