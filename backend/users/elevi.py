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


# --- 1. GET: Returnează toți elevii ---
@elevi_bp.get("/api/elevi")
@token_required
def get_students():
    con = get_conn()
    try:
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
                    copil["parinte_id"] = parinte_id
                    copil["parinte_nume"] = parinte_nume
                    toti_elevii.append(copil)

        return jsonify(toti_elevii)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 2. POST: Adaugă un elev ---
@elevi_bp.post("/api/elevi")
@token_required
def add_student():
    data = request.get_json(silent=True) or {}

    nume_elev = _normalize(data.get("nume"))
    varsta = data.get("varsta")
    gen = data.get("gen")
    grupa = _normalize(data.get("grupa"))

    parinte_id = data.get("parinte_id")
    parinte_nume = _normalize(data.get("parent_display") or data.get("parinte_nume"))

    if not nume_elev:
        return jsonify({"status": "error", "message": "Numele elevului este obligatoriu"}), 400

    con = get_conn()
    try:
        target_parent_id = None
        copii_list = []

        if parinte_id:
            # A. Părinte existent
            row = con.execute("SELECT id, copii FROM utilizatori WHERE id = %s", (parinte_id,)).fetchone()
            if not row:
                return jsonify({"status": "error", "message": "Părintele selectat nu mai există."}), 404
            target_parent_id = row["id"]
            copii_list = _safe_load_list(row["copii"])

        elif parinte_nume:
            # B. Părinte nou (Placeholder)
            # Verificăm unicitatea
            check = con.execute("SELECT id FROM utilizatori WHERE LOWER(username) = LOWER(%s)",
                                (parinte_nume,)).fetchone()
            if check:
                return jsonify({"status": "error",
                                "message": "Există deja un părinte cu acest nume. Selectează-l din listă."}), 409

            # Generăm cod de revendicare
            claim_code = uuid.uuid4().hex[:8].upper()
            # Email dummy pentru a nu crăpa la constrângerea UNIQUE (dacă există)
            dummy_email = f"placeholder_{claim_code}@hwarang.temp"

            # --- AICI ESTE MODIFICAREA: IMPUNEM ROLUL 'Parinte' ---
            cur = con.execute("""
                INSERT INTO utilizatori (
                    username, 
                    email,
                    parola, 
                    rol,               -- Coloana rol
                    is_placeholder, 
                    claim_code, 
                    copii, 
                    grupe
                )
                VALUES (%s, %s, 'NO_LOGIN', 'Parinte', 1, %s, '[]', '')
                RETURNING id
            """, (parinte_nume, dummy_email, claim_code))

            try:
                new_row = cur.fetchone()
                target_parent_id = new_row['id'] if new_row else cur.lastrowid
            except:
                target_parent_id = cur.lastrowid

            copii_list = []
        else:
            return jsonify(
                {"status": "error", "message": "Trebuie să selectezi un părinte sau să introduci un nume nou."}), 400

        # C. Adăugăm copilul
        new_child = {
            "id": uuid.uuid4().hex,
            "nume": nume_elev,
            "varsta": varsta,
            "gen": gen,
            "grupa": grupa
        }
        copii_list.append(new_child)

        # D. Salvăm
        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(copii_list, ensure_ascii=False), target_parent_id)
        )
        _update_grupe_column(con, target_parent_id, copii_list)
        con.commit()

        return jsonify({"status": "success", "message": "Elev adăugat cu succes."}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 3. PATCH: Modifică un elev existent (și numele părintelui) ---
@elevi_bp.patch("/api/elevi/<string:elev_id>")
@token_required
def update_student(elev_id):
    data = request.get_json(silent=True) or {}

    con = get_conn()
    try:
        rows = con.execute(
            "SELECT id, copii, is_placeholder, username, nume_complet FROM utilizatori WHERE copii IS NOT NULL").fetchall()

        parent_found_row = None
        copii_list = []
        child_found = False

        # 1. Găsim copilul
        for r in rows:
            c_list = _safe_load_list(r["copii"])
            for i, child in enumerate(c_list):
                if child.get("id") == elev_id:
                    parent_found_row = r
                    copii_list = c_list

                    if "nume" in data: child["nume"] = _normalize(data["nume"])
                    if "varsta" in data: child["varsta"] = data["varsta"]
                    if "gen" in data: child["gen"] = data["gen"]
                    if "grupa" in data: child["grupa"] = _normalize(data["grupa"])

                    c_list[i] = child
                    child_found = True
                    break
            if child_found:
                break

        if not child_found:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

        parent_id = parent_found_row["id"]

        # 2. Actualizăm Numele Părintelui
        nume_parinte_nou = _normalize(data.get("parinte_nume") or data.get("parent_display"))

        if nume_parinte_nou:
            nume_vechi = (parent_found_row["nume_complet"] or parent_found_row["username"] or "").strip()

            if nume_parinte_nou.lower() != nume_vechi.lower():
                is_placeholder = parent_found_row["is_placeholder"]

                if is_placeholder == 1:
                    # Dacă e placeholder, putem schimba username-ul
                    try:
                        con.execute(
                            "UPDATE utilizatori SET username = %s, nume_complet = %s WHERE id = %s",
                            (nume_parinte_nou, nume_parinte_nou, parent_id)
                        )
                    except:
                        con.execute(
                            "UPDATE utilizatori SET nume_complet = %s WHERE id = %s",
                            (nume_parinte_nou, parent_id)
                        )
                else:
                    # Dacă e cont real, schimbăm doar numele de afișare
                    con.execute(
                        "UPDATE utilizatori SET nume_complet = %s WHERE id = %s",
                        (nume_parinte_nou, parent_id)
                    )

        # 3. Salvăm
        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(copii_list, ensure_ascii=False), parent_id)
        )
        _update_grupe_column(con, parent_id, copii_list)
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
            new_list = [c for c in c_list if c.get("id") != elev_id]

            if len(new_list) < len(c_list):
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


# --- 5. SUGESTII ---
@elevi_bp.get("/api/profil/sugestii_inscriere")
@token_required
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
                    if isinstance(c, dict):
                        copii.append({"nume": c.get("nume"), "grupa": c.get("grupa")})

        elif rol == 'sportiv':
            # Dacă e sportiv, se înscrie pe el însuși
            pass

        return jsonify({"status": "success", "data": {"rol": rol, "nume_propriu": nume, "copii": copii}})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500