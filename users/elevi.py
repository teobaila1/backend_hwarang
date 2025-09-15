# backend/users/elevi.py
import json, uuid, re
from flask import Blueprint, request, jsonify
from backend.config import get_conn

elevi_bp = Blueprint("elevi", __name__)

# ----------------- helpers -----------------
def _normalize_grupa(value):
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r'^\s*(?:grupa\s*)?(\d+)\s*$', s, re.IGNORECASE)
    return f"Grupa {m.group(1)}" if m else s

def _normalize_text(s):
    s = (s or "").strip()
    return re.sub(r"\s+", " ", s)

def _safe_load_children(copii_json):
    if not copii_json:
        return []
    try:
        v = json.loads(copii_json)
        return v if isinstance(v, list) else []
    except Exception:
        return []

def _table_has_column(con, table, column):
    cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols

def _update_field_by_id_or_username(con, parent_id, parent_username, field, value):
    """Face UPDATE fie după id, fie (fallback) după username (case-insensitive)."""
    if parent_id is not None:
        con.execute(f"UPDATE utilizatori SET {field} = ? WHERE id = ?", (value, parent_id))
    else:
        con.execute(f"UPDATE utilizatori SET {field} = ? WHERE LOWER(username) = LOWER(?)",
                    (value, parent_username))

def _save_parent_children(con, parent_id, parent_username, children):
    _update_field_by_id_or_username(
        con, parent_id, parent_username, "copii",
        json.dumps(children, ensure_ascii=False)
    )

def _ensure_child_ids(children):
    changed = False
    for c in children:
        if not c.get("id"):
            c["id"] = uuid.uuid4().hex
            changed = True
        if "varsta" in c:
            try:
                c["varsta"] = int(c["varsta"])
            except Exception:
                pass
        if "grupa" in c:
            ng = _normalize_grupa(c["grupa"])
            if ng != c["grupa"]:
                c["grupa"] = ng
                changed = True
    return changed, children

def _find_parent_of_child(con, child_id):
    """
    Returnează (parent_id, parent_username, children, idx).
    parent_id poate fi None (schema ta curentă), caz în care folosim username la UPDATE-uri.
    """
    rows = con.execute("SELECT id, username, copii FROM utilizatori").fetchall()
    for r in rows:
        parent_id = r["id"]
        parent_username = r["username"]
        children = _safe_load_children(r["copii"])
        for idx, c in enumerate(children):
            if str(c.get("id")) == str(child_id):
                return parent_id, parent_username, children, idx
    return None, None, None, None

# backend/users/elevi.py  (înlocuiește integral funcția asta)
def _create_placeholder_parent_by_name(con, parent_name):
    """
    Creează un părinte placeholder cu username=parent_name.
    Refolosește placeholder existent; dacă username-ul e ocupat, creează `<nume> (2)`, `(3)` etc.
    Returnează (parent_id_posibil, username_folosit, err).
    """
    uname = _normalize_text(parent_name)
    if not uname:
        return None, None, "Numele părintelui este obligatoriu."

    # Refolosește placeholder existent (exact același username)
    row = con.execute(
        "SELECT id, username FROM utilizatori "
        "WHERE LOWER(rol)='parinte' AND is_placeholder=1 AND LOWER(username)=LOWER(?)",
        (uname,)
    ).fetchone()
    if row:
        return row["id"], row["username"], None

    # Găsește un username liber
    base = uname
    cand = base
    i = 1
    while con.execute("SELECT 1 FROM utilizatori WHERE LOWER(username)=LOWER(?)", (cand,)).fetchone():
        i += 1
        cand = f"{base} ({i})"

    # Construiește dinamic lista de coloane/valori
    cols = ["rol", "username", "email", "copii", "grupe"]
    vals = ["parinte", cand, None, "[]", ""]

    if _table_has_column(con, "utilizatori", "is_placeholder"):
        cols.append("is_placeholder"); vals.append(1)
    if _table_has_column(con, "utilizatori", "claim_code"):
        cols.append("claim_code"); vals.append(uuid.uuid4().hex[:8].upper())
    if _table_has_column(con, "utilizatori", "created_by_trainer"):
        cols.append("created_by_trainer"); vals.append(1)
    if _table_has_column(con, "utilizatori", "nume_complet"):
        cols.append("nume_complet"); vals.append(uname)  # sau cand

    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO utilizatori ({', '.join(cols)}) VALUES ({placeholders})"
    cur = con.execute(sql, tuple(vals))

    parent_id = cur.lastrowid
    return parent_id, cand, None

# -------------------------------------------



@elevi_bp.post("/api/elevi")
def create_elev():
    data = request.get_json(silent=True) or {}

    # numele ELEVULUI (acceptăm 'nume' sau fallback 'username')
    nume   = _normalize_text(data.get("nume") or data.get("username"))
    varsta = data.get("varsta")
    grupa  = _normalize_grupa(data.get("grupa"))
    gen    = (data.get("gen") or None)

    # fie parinte_id (părinte existent), fie parinte_nume (doar numele părintelui -> creăm placeholder)
    parent_id   = data.get("parinte_id")
    parent_nume = _normalize_text(data.get("parinte_nume"))

    if not nume or varsta is None or not grupa:
        return jsonify({
            "status": "error",
            "message": "Câmpuri obligatorii: nume, varsta, grupa (și parinte_id sau parinte_nume)."
        }), 400

    try:
        varsta = int(varsta)
    except Exception:
        return jsonify({"status": "error", "message": "Vârsta trebuie să fie număr."}), 400

    con = get_conn()
    try:
        # 1) Determinăm părintele
        parent_username = None

        if parent_id:
            parent_row = con.execute(
                "SELECT id, username, copii, grupe FROM utilizatori WHERE id = ?",
                (parent_id,)
            ).fetchone()
            if not parent_row:
                return jsonify({"status": "error", "message": "Părinte inexistent."}), 404
            parent_id_final = parent_row["id"]
            parent_username = parent_row["username"]

        elif parent_nume:
            # a) Refolosește placeholder existent
            parent_row = con.execute(
                "SELECT id, username, copii, grupe FROM utilizatori "
                "WHERE LOWER(rol)='parinte' AND is_placeholder=1 AND LOWER(username)=LOWER(?) "
                "ORDER BY rowid DESC LIMIT 1",
                (parent_nume,)
            ).fetchone()

            # b) Creează unul nou dacă nu există
            if not parent_row:
                new_id, uname_used, err = _create_placeholder_parent_by_name(con, parent_nume)
                if err:
                    con.rollback()
                    return jsonify({"status": "error", "message": err}), 400

                # citește rândul proaspăt creat
                parent_row = con.execute(
                    "SELECT id, username, copii, grupe FROM utilizatori "
                    "WHERE LOWER(rol)='parinte' AND LOWER(username)=LOWER(?) "
                    "ORDER BY rowid DESC LIMIT 1",
                    (uname_used,)
                ).fetchone()

            if not parent_row:
                con.rollback()
                return jsonify({"status": "error", "message": "Nu s-a putut crea părintele placeholder."}), 500

            parent_id_final = parent_row["id"]      # poate fi None pe schema ta
            parent_username = parent_row["username"]

        else:
            return jsonify({"status": "error", "message": "Trimite fie parinte_id, fie parinte_nume."}), 400

        # 2) Adăugăm elevul în lista de copii a părintelui
        children = _safe_load_children(parent_row["copii"])
        _, children = _ensure_child_ids(children)

        new_child = {
            "id": uuid.uuid4().hex,
            "nume": nume,
            "varsta": varsta,
            "grupa": grupa,
            "gen": gen
        }
        children.append(new_child)
        _save_parent_children(con, parent_id_final, parent_username, children)

        # 3) Actualizăm 'grupe' (fără duplicate, cu normalizare)
        existing_grupe = [g.strip() for g in (parent_row["grupe"] or "").split(",") if g.strip()]
        existing_norm = { _normalize_grupa(g).lower(): g for g in existing_grupe }
        gkey = (grupa or "").lower()
        if gkey and gkey not in existing_norm:
            existing_grupe.append(grupa)
            _update_field_by_id_or_username(
                con, parent_id_final, parent_username, "grupe", ", ".join(existing_grupe)
            )

        con.commit()
        return jsonify({"status": "success", "id": new_child["id"], "parinte_id": parent_id_final}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500



@elevi_bp.patch("/api/elevi/<child_id>")
def patch_elev(child_id):
    data = request.get_json(silent=True) or {}

    nume = (data.get("nume") or "").strip()
    gen = (data.get("gen") or "").strip()
    grupa = _normalize_grupa(data.get("grupa"))
    varsta = data.get("varsta")
    parent_name = (data.get("parent_name") or "").strip()

    con = get_conn()
    cur = con.cursor()

    # găsește părintele care deține acest copil
    rows = cur.execute("""
        SELECT id, username, nume_complet, copii
        FROM utilizatori
        WHERE LOWER(rol)='parinte' AND copii IS NOT NULL AND copii <> ''
    """).fetchall()

    found = False
    for r in rows:
        try:
            copii = json.loads(r["copii"] or "[]")
        except Exception:
            copii = []

        changed = False
        for c in copii:
            if str(c.get("id")) == str(child_id):
                if nume:   c["nume"]   = nume
                if gen:    c["gen"]    = gen
                if grupa:  c["grupa"]  = grupa
                if varsta is not None:
                    try: c["varsta"] = int(varsta)
                    except Exception: pass
                changed = True
                found = True
                break

        if changed:
            cur.execute(
                "UPDATE utilizatori SET copii = ? WHERE id = ?",
                (json.dumps(copii, ensure_ascii=False), r["id"])
            )

            # ✨ la nevoie, actualizăm și numele părintelui
            if parent_name:
                cur.execute(
                    "UPDATE utilizatori SET nume_complet = ? WHERE id = ?",
                    (parent_name, r["id"])
                )

            con.commit()
            return jsonify({"status": "success"})

    if not found:
        return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404



@elevi_bp.patch("/api/elevi/<child_id>")
def update_elev(child_id):
    data = request.get_json(silent=True) or {}
    allowed = {"nume", "varsta", "grupa", "gen"}
    payload = {k: v for k, v in data.items() if k in allowed}

    if "nume" in payload:
        payload["nume"] = _normalize_text(payload["nume"])
    if "grupa" in payload and payload["grupa"] is not None:
        payload["grupa"] = _normalize_grupa(payload["grupa"])
    if "varsta" in payload:
        try:
            payload["varsta"] = int(payload["varsta"])
        except Exception:
            return jsonify({"status": "error", "message": "Vârsta trebuie să fie număr."}), 400

    con = get_conn()
    try:
        parent_id, parent_username, children, idx = _find_parent_of_child(con, child_id)
        if parent_id is None and parent_username is None:
            return jsonify({"status": "error", "message": "Elev inexistent."}), 404

        children[idx].update(payload)
        _save_parent_children(con, parent_id, parent_username, children)

        # actualizează grupe după editare
        grupe_seen = []
        for c in children:
            g = _normalize_grupa(c.get("grupa"))
            if g and g not in grupe_seen:
                grupe_seen.append(g)
        _update_field_by_id_or_username(con, parent_id, parent_username, "grupe", ", ".join(grupe_seen))

        con.commit()
        return jsonify({"status": "success"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@elevi_bp.delete("/api/elevi/<child_id>")
def delete_elev(child_id):
    con = get_conn()
    try:
        parent_id, parent_username, children, idx = _find_parent_of_child(con, child_id)
        if parent_id is None and parent_username is None:
            return jsonify({"status": "error", "message": "Elev inexistent."}), 404

        children.pop(idx)
        _save_parent_children(con, parent_id, parent_username, children)

        # recalc grupe
        grupe_seen = []
        for c in children:
            g = _normalize_grupa(c.get("grupa"))
            if g and g not in grupe_seen:
                grupe_seen.append(g)
        _update_field_by_id_or_username(con, parent_id, parent_username, "grupe", ", ".join(grupe_seen))

        con.commit()
        return jsonify({"status": "success"}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
