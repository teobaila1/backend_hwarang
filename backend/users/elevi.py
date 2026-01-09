# backend/users/elevi.py
import json
import re
import uuid
from flask import Blueprint, request, jsonify
from backend.config import get_conn

elevi_bp = Blueprint("elevi", __name__)


def _normalize(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def _safe_load_list(s):
    if not s: return []
    try:
        if isinstance(s, list): return s
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except:
        return []


# --- 1. GET: Returnează toți elevii ---
@elevi_bp.get("/api/elevi")
def get_students():
    con = get_conn()
    try:
        rows = con.execute("""
            SELECT id, nume_complet, username, copii 
            FROM utilizatori 
            WHERE copii IS NOT NULL
        """).fetchall()

        toti_elevii = []
        for r in rows:
            # Convertim în dict pentru siguranță
            row_dict = dict(r)
            parinte_nume = row_dict.get("nume_complet") or row_dict.get("username")
            parinte_id = row_dict.get("id")

            copii_list = _safe_load_list(row_dict.get("copii"))

            for copil in copii_list:
                if isinstance(copil, dict):
                    copil["parinte_id"] = parinte_id
                    copil["parinte_nume"] = parinte_nume
                    toti_elevii.append(copil)

        return jsonify(toti_elevii)
    except Exception as e:
        print(f"Eroare GET elevi: {e}")
        return jsonify([])


# --- 2. POST: Adaugă un elev ---
@elevi_bp.post("/api/elevi")
def add_student():
    data = request.get_json(silent=True) or {}
    print(f"DEBUG: Date primite la POST /api/elevi: {data}")

    # Preluăm datele EXACT cum vin din frontend
    nume_elev = _normalize(data.get("nume"))
    varsta = data.get("varsta")
    gen = data.get("gen")
    grupa = data.get("grupa")

    # FIX: Aici era problema - frontend trimite 'parinte_nume', nu 'nume_parinte'
    nume_parinte = _normalize(data.get("parinte_nume"))

    if not nume_elev:
        return jsonify({"status": "error", "message": "Numele elevului este obligatoriu."}), 400

    if not nume_parinte:
        return jsonify({"status": "error", "message": "Trebuie să introduci numele părintelui."}), 400

    con = get_conn()
    try:
        # Căutăm părintele existent după nume
        row = con.execute("""
            SELECT id, copii FROM utilizatori 
            WHERE LOWER(username) = LOWER(%s) OR LOWER(nume_complet) = LOWER(%s)
            LIMIT 1
        """, (nume_parinte, nume_parinte)).fetchone()

        if row:
            row_dict = dict(row)
            parent_id = row_dict["id"]
            copii_existenti = _safe_load_list(row_dict["copii"])
        else:
            # Creăm un părinte nou (placeholder)
            claim_code = uuid.uuid4().hex[:8].upper()
            cur = con.execute("""
                INSERT INTO utilizatori (rol, username, nume_complet, is_placeholder, claim_code, created_by_trainer, copii)
                VALUES ('parinte', %s, %s, 1, %s, 1, '[]')
                RETURNING id
            """, (nume_parinte, nume_parinte, claim_code))

            try:
                new_row = cur.fetchone()
                parent_id = new_row['id'] if new_row else cur.lastrowid
            except:
                parent_id = cur.lastrowid

            copii_existenti = []

        # Creăm obiectul copil
        new_child = {
            "id": uuid.uuid4().hex,
            "nume": nume_elev,
            "varsta": varsta,
            "gen": gen,
            "grupa": grupa
        }
        copii_existenti.append(new_child)

        # Salvăm înapoi în baza de date
        con.execute("""
            UPDATE utilizatori 
            SET copii = %s 
            WHERE id = %s
        """, (json.dumps(copii_existenti, ensure_ascii=False), parent_id))

        con.commit()

        return jsonify({
            "status": "success",
            "message": f"Elev adăugat la părintele {nume_parinte}.",
            "elev": new_child
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Eroare add_student: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 3. DELETE: Șterge un elev ---
@elevi_bp.delete("/api/elevi/<string:elev_id>")
def delete_student(elev_id):
    con = get_conn()
    try:
        # Căutăm toți userii cu copii (fallback sigur pentru orice versiune Postgres/driver)
        rows = con.execute("SELECT id, copii FROM utilizatori WHERE copii IS NOT NULL").fetchall()

        parent_found = None
        new_copii_list = []

        for r in rows:
            r_dict = dict(r)
            copii = _safe_load_list(r_dict["copii"])

            original_len = len(copii)
            filtered = [c for c in copii if c.get("id") != elev_id]

            if len(filtered) < original_len:
                parent_found = r_dict["id"]
                new_copii_list = filtered
                break

        if parent_found:
            con.execute("""
                UPDATE utilizatori SET copii = %s WHERE id = %s
            """, (json.dumps(new_copii_list, ensure_ascii=False), parent_found))
            con.commit()
            return jsonify({"status": "success", "message": "Elev șters."})
        else:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 4. SUGESTII (pentru dropdown înscriere) ---
@elevi_bp.get("/api/profil/sugestii_inscriere")
def sugestii_inscriere():
    username = request.args.get('username')
    if not username: return jsonify({"status": "error", "message": "Username lipsă"}), 400

    try:
        con = get_conn()
        row = con.execute("SELECT rol, nume_complet, copii FROM utilizatori WHERE username=%s", (username,)).fetchone()

        if not row: return jsonify({"status": "error", "message": "User not found"}), 404

        u = dict(row)
        rol = (u.get("rol") or "").lower()
        nume = u.get("nume_complet") or username
        copii = []

        if rol in ['parinte', 'admin']:
            raw = u.get("copii")
            if raw:
                lst = _safe_load_list(raw)
                for c in lst:
                    if c.get("nume"):
                        # Trimitem și grupa, util pentru dropdown
                        copii.append({"nume": c.get("nume"), "grupa": c.get("grupa", "")})

        return jsonify({"status": "success", "data": {"rol": rol, "nume_propriu": nume, "copii": copii}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500