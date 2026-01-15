# backend/users/toate_grupele_antrenori.py
import json
import re
import uuid
from flask import Blueprint, jsonify

from ..accounts.decorators import token_required, admin_required
from ..config import get_conn

toate_grupele_antrenori_bp = Blueprint('toate_grupele_antrenori', __name__)


def normalize_grupa(value):
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r'^\s*(?:grupa\s*)?(\d+)\s*$', s, re.IGNORECASE)
    return f"Grupa {m.group(1)}" if m else s


def _safe_load_children(raw):
    try:
        v = json.loads(raw or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _group_sort_key(name: str):
    m = re.search(r"(\d+)", name or "")
    return int(m.group(1)) if m else 9999


def ensure_child_ids_and_normalize(children):
    """
    Verifică fiecare copil. Dacă nu are ID, îi generează unul.
    Normalizează grupa și vârsta.
    Returnează (True, lista_noua) dacă s-a modificat ceva.
    """
    changed = False
    for c in children:
        # 1. Generare ID
        if "id" not in c or not c["id"]:
            c["id"] = uuid.uuid4().hex
            changed = True

        # 2. Normalizare vârstă
        if "varsta" in c and isinstance(c["varsta"], str) and c["varsta"].isdigit():
            c["varsta"] = int(c["varsta"])
            changed = True

        # 3. Normalizare grupă
        if "grupa" in c:
            ng = normalize_grupa(c["grupa"])
            if ng != c["grupa"]:
                c["grupa"] = ng
                changed = True
    return changed, children


@toate_grupele_antrenori_bp.get("/api/toate_grupele_antrenori")
@token_required
@admin_required
def toate_grupele_antrenori():
    con = get_conn()

    # --- 1. AUTO-REPAIR: Reparăm copiii fără ID din toată baza de date ---
    try:
        # Luăm toți utilizatorii care au copii
        users_with_kids = con.execute("SELECT id, copii FROM utilizatori WHERE copii IS NOT NULL").fetchall()

        for u in users_with_kids:
            children = _safe_load_children(u["copii"])
            if not children:
                continue

            # Verificăm și reparăm
            was_changed, fixed_children = ensure_child_ids_and_normalize(children)

            if was_changed:
                # Salvăm înapoi în DB imediat
                con.execute(
                    "UPDATE utilizatori SET copii = %s WHERE id = %s",
                    (json.dumps(fixed_children, ensure_ascii=False), u["id"])
                )
                con.commit()
    except Exception as e:
        print(f"[WARN] Eroare la auto-repair admin: {e}")
        # Continuăm execuția chiar dacă auto-repair dă eroare, ca să afișăm datele

    # --- 2. Interogare date pentru afișare ---

    # Antrenorii + Adminii care antrenează
    trainers = con.execute("""
            SELECT id, username, COALESCE(nume_complet, username) AS display_name, grupe 
            FROM utilizatori 
            WHERE LOWER(rol) = 'antrenor' 
               OR (LOWER(rol) = 'admin' AND grupe IS NOT NULL AND length(grupe) > 0)
        """).fetchall()

    # Părinții (luăm datele proaspete, posibil reparate mai sus)
    parents = con.execute("""
        SELECT username, email,
               COALESCE(nume_complet, username) AS display_name,
               copii
        FROM utilizatori
        WHERE LOWER(rol) IN ('parinte', 'admin')
    """).fetchall()

    parsed_parents = []
    for p in parents:
        kids = _safe_load_children(p["copii"])
        if not kids:
            continue
        parsed_parents.append({
            "username": p["username"],
            "email": p["email"],
            "display": p["display_name"],
            "copii": kids
        })

    out = []

    for tr in trainers:
        groups_raw = [g.strip() for g in (tr["grupe"] or "").split(",") if g.strip()]
        groups = [normalize_grupa(g) for g in groups_raw]
        groups = [g for g in groups if g]

        groups_map = {g: [] for g in groups}

        for p in parsed_parents:
            for c in p["copii"]:
                g = normalize_grupa(c.get("grupa"))
                if g in groups_map:
                    groups_map[g].append({
                        "id": c.get("id"),
                        "nume": c.get("nume"),
                        "varsta": c.get("varsta"),
                        "gen": c.get("gen"),
                        "grupa": g,
                        "_parent": {
                            "username": p["username"],
                            "email": p["email"],
                            "display": p["display"]
                        }
                    })

        grupe_list = [
            {"grupa": g, "copii": sorted(groups_map[g], key=lambda k: (str(k.get("nume") or "").lower()))}
            for g in sorted(groups_map.keys(), key=_group_sort_key)
        ]

        out.append({
            "antrenor": tr["username"],
            "antrenor_display": tr["display_name"],
            "grupe": grupe_list
        })

    out.sort(key=lambda r: (r.get("antrenor_display") or r.get("antrenor") or "").lower())

    return jsonify({"status": "success", "data": out}), 200