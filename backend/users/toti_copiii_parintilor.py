import json
import re
import uuid
from flask import Blueprint, jsonify, request
from ..accounts.decorators import admin_required, token_required
from ..config import get_conn

toti_copiii_parintilor_bp = Blueprint('copiii_parintilor', __name__)


def _safe_load_list(s):
    if not s: return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except:
        return []


def _normalize_grupa(value):
    if not value: return None
    s = str(value).strip()
    m = re.match(r'^\s*(?:grupa\s*)?(\d+)\s*$', s, re.IGNORECASE)
    return f"Grupa {m.group(1)}" if m else s


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    gn = str(group_name).strip()
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (gn,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (gn,))
    return cur.fetchone()['id']


# --- LISTARE TOȚI COPIII (Admin) ---
@toti_copiii_parintilor_bp.get("/api/toti_copiii")
@token_required
@admin_required
def toti_copiii():
    try:
        con = get_conn()
        cur = con.cursor()
        # Citim din tabelele noi
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
            map_parinti[pid]["copii"].append({
                "id": r['id'],
                "nume": r['nume'],
                "varsta": str(r['data_nasterii']) if r['data_nasterii'] else "",
                "gen": r['gen'],
                "grupa": r['grupa_text']
            })

        return jsonify({"status": "success", "date": list(map_parinti.values())}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ADĂUGARE COPIL (Admin/Antrenor pt Părinte) ---
@toti_copiii_parintilor_bp.post("/api/adauga_copil")
@token_required
def adauga_copil():
    data = request.get_json(silent=True) or {}
    target_username = data.get("parinte_username")
    nume = data.get("nume")
    grupa = data.get("grupa")
    gen = data.get("gen")

    if not target_username or not nume:
        return jsonify({"status": "error", "message": "Date incomplete"}), 400

    try:
        con = get_conn()
        cur = con.cursor()

        # Găsim ID părinte
        cur.execute("SELECT id FROM utilizatori WHERE username = %s", (target_username,))
        row = cur.fetchone()
        if not row: return jsonify({"status": "error", "message": "Părinte inexistent"}), 404
        pid = row['id']

        new_id = uuid.uuid4().hex

        # Insert în tabelul COPII
        cur.execute("""
            INSERT INTO copii (id, id_parinte, nume, gen, grupa_text, added_by_trainer)
            VALUES (%s, %s, %s, %s, %s, TRUE)
        """, (new_id, pid, nume, gen, grupa))

        # Insert în SPORTIVI_PE_GRUPE
        if grupa:
            gid = _get_or_create_group_id(cur, grupa)
            if gid:
                cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)", (gid, new_id))

        con.commit()
        return jsonify({"status": "success", "message": "Copil adăugat!"}), 200
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ADMIN: DELETE PĂRINTE ---
@toti_copiii_parintilor_bp.delete("/api/admin/parinte/<parent_username>")
@token_required
@admin_required
def admin_delete_parent(parent_username):
    try:
        con = get_conn()
        cur = con.cursor()

        # Datorită 'ON DELETE CASCADE' definit în scriptul SQL,
        # ștergerea userului șterge automat copiii, rolurile și legăturile cu grupele.
        cur.execute("DELETE FROM utilizatori WHERE username=%s", (parent_username,))

        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Utilizatorul nu există."}), 404

        con.commit()
        return jsonify({"status": "success", "message": "Părinte șters."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ADMIN: UPDATE PĂRINTE ---
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

        # Verificăm duplicat username
        if new_username.lower() != parent_username.lower():
            cur.execute("SELECT 1 FROM utilizatori WHERE LOWER(username)=LOWER(%s)", (new_username,))
            if cur.fetchone():
                return jsonify({"status": "error", "message": "Username deja folosit."}), 409

        # Update simplu (datele astea sunt încă în tabelul utilizatori)
        cur.execute("""
            UPDATE utilizatori 
            SET username=%s, email=%s, nume_complet=%s 
            WHERE username=%s
        """, (new_username, email, nume_complet, parent_username))

        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Părinte inexistent."}), 404

        con.commit()
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500