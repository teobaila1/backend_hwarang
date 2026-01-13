# backend/users/elevi.py
import json
import re
import uuid
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from ..accounts.decorators import token_required

elevi_bp = Blueprint("elevi", __name__)


# --- HELPERS ---
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


def _update_grupe_column(con, parent_id, copii_list):
    """Recalculează coloana 'grupe' (text) pe baza listei de copii."""
    grupe_set = set()
    for c in copii_list:
        g = (c.get("grupa") or "").strip()
        if g:
            grupe_set.add(g)

    grupe_str = ", ".join(sorted(grupe_set))
    con.execute("UPDATE utilizatori SET grupe = %s WHERE id = %s", (grupe_str, parent_id))


# --- 1. GET: Returnează toți elevii (pentru Admin/Antrenor) ---
@elevi_bp.get("/api/elevi")
@token_required
def get_students():
    con = get_conn()
    try:
        # Luăm părinții care au copii
        rows = con.execute("""
            SELECT id, nume_complet, username, email, copii 
            FROM utilizatori 
            WHERE copii IS NOT NULL
        """).fetchall()

        toti_elevii = []
        for r in rows:
            row_dict = dict(r)
            parinte_nume = row_dict.get("nume_complet") or row_dict.get("username")
            parinte_id = row_dict.get("id")

            copii_list = _safe_load_list(row_dict.get("copii"))

            for copil in copii_list:
                if isinstance(copil, dict):
                    # Îi atașăm și datele părintelui ca să știm al cui e
                    copil["parinte_id"] = parinte_id
                    copil["parinte_nume"] = parinte_nume
                    toti_elevii.append(copil)

        return jsonify(toti_elevii)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 2. POST: Adaugă un elev (Antrenorul poate face asta) ---
@elevi_bp.post("/api/elevi")
@token_required
def add_student():
    data = request.get_json(silent=True) or {}

    # Date copil
    nume_elev = _normalize(data.get("nume"))
    varsta = data.get("varsta")
    gen = data.get("gen")
    grupa = _normalize(data.get("grupa"))

    # Identificare Părinte
    parinte_id = data.get("parinte_id")  # Dacă e părinte existent
    parinte_nume = _normalize(data.get("parent_display") or data.get("parinte_nume"))  # Dacă e părinte nou

    if not nume_elev:
        return jsonify({"status": "error", "message": "Numele elevului este obligatoriu"}), 400

    con = get_conn()
    try:
        target_parent_id = None
        copii_list = []

        # A. Cazul: Părinte Existent (selectat din listă)
        if parinte_id:
            row = con.execute("SELECT id, copii FROM utilizatori WHERE id = %s", (parinte_id,)).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Părintele selectat nu mai există."}), 404
            target_parent_id = row["id"]
            copii_list = _safe_load_list(row["copii"])

        # B. Cazul: Părinte Nou (create placeholder)
        elif parinte_nume:
            # Verificăm dacă există deja unul cu acest username
            check = con.execute("SELECT id FROM utilizatori WHERE LOWER(username) = LOWER(%s)",
                                (parinte_nume,)).fetchone()
            if check:
                return jsonify({"status": "error",
                                "message": "Există deja un părinte cu acest nume. Selectează-l din listă."}), 409

            # Creăm cont placeholder
            claim_code = uuid.uuid4().hex[:8].upper()
            cur = con.execute("""
                INSERT INTO utilizatori (username, role, rol, is_placeholder, claim_code, copii, grupe)
                VALUES (%s, 'parinte', 'Parinte', 1, %s, '[]', '')
                RETURNING id
            """, (parinte_nume, claim_code))

            # Compatibilitate ID (unele drivere nu suporta RETURNING direct in fetchone)
            try:
                new_row = cur.fetchone()
                target_parent_id = new_row['id'] if new_row else cur.lastrowid
            except:
                target_parent_id = cur.lastrowid

            copii_list = []
        else:
            return jsonify(
                {"status": "error", "message": "Trebuie să selectezi un părinte sau să introduci un nume nou."}), 400

        # C. Adăugăm copilul în listă
        new_child = {
            "id": uuid.uuid4().hex,
            "nume": nume_elev,
            "varsta": varsta,
            "gen": gen,
            "grupa": grupa
        }
        copii_list.append(new_child)

        # D. Salvăm în DB
        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(copii_list, ensure_ascii=False), target_parent_id)
        )

        # Actualizăm și coloana 'grupe' pentru filtrare rapidă
        _update_grupe_column(con, target_parent_id, copii_list)

        con.commit()

        return jsonify({"status": "success", "message": "Elev adăugat cu succes."}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 3. PATCH: Modifică un elev existent ---
@elevi_bp.patch("/api/elevi/<string:elev_id>")
@token_required
def update_student(elev_id):
    data = request.get_json(silent=True) or {}

    con = get_conn()
    try:
        # Căutăm părintele care are acest copil în JSON
        # Aceasta este o căutare puțin ineficientă dar sigură pe structura actuală
        rows = con.execute("SELECT id, copii FROM utilizatori WHERE copii IS NOT NULL").fetchall()

        parent_found = None
        copii_list = []
        child_found = False

        for r in rows:
            c_list = _safe_load_list(r["copii"])
            for i, child in enumerate(c_list):
                if child.get("id") == elev_id:
                    # Am găsit copilul!
                    parent_found = r["id"]
                    copii_list = c_list

                    # Actualizăm câmpurile
                    if "nume" in data: child["nume"] = _normalize(data["nume"])
                    if "varsta" in data: child["varsta"] = data["varsta"]
                    if "gen" in data: child["gen"] = data["gen"]
                    if "grupa" in data: child["grupa"] = _normalize(data["grupa"])

                    # Salvăm modificarea în lista temporară
                    c_list[i] = child
                    child_found = True
                    break
            if child_found:
                break

        if not child_found:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

        # Salvăm în DB
        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(copii_list, ensure_ascii=False), parent_found)
        )
        _update_grupe_column(con, parent_found, copii_list)
        con.commit()

        return jsonify({"status": "success", "message": "Date actualizate."}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 4. DELETE: Șterge un elev ---
@elevi_bp.delete("/api/elevi/<string:elev_id>")
@token_required
def delete_student(elev_id):
    con = get_conn()
    try:
        rows = con.execute("SELECT id, copii FROM utilizatori WHERE copii IS NOT NULL").fetchall()

        parent_found = None
        copii_list = []
        child_found = False

        for r in rows:
            c_list = _safe_load_list(r["copii"])
            # Filtrăm lista ca să scoatem copilul
            new_list = [c for c in c_list if c.get("id") != elev_id]

            if len(new_list) < len(c_list):
                # Înseamnă că am scos ceva -> am găsit copilul
                parent_found = r["id"]
                copii_list = new_list
                child_found = True
                break

        if child_found:
            con.execute(
                "UPDATE utilizatori SET copii = %s WHERE id = %s",
                (json.dumps(copii_list, ensure_ascii=False), parent_found)
            )
            _update_grupe_column(con, parent_found, copii_list)
            con.commit()
            return jsonify({"status": "success", "message": "Elev șters."})
        else:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 4. SUGESTII ---
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
                        copii.append({"nume": c.get("nume"), "grupa": c.get("grupa", "")})

        return jsonify({"status": "success", "data": {"rol": rol, "nume_propriu": nume, "copii": copii}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500