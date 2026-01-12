# backend/users/toate_grupele_antrenori.py
import json
import re
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

@toate_grupele_antrenori_bp.get("/api/toate_grupele_antrenori")
@token_required
@admin_required
def toate_grupele_antrenori():
    con = get_conn()

    # 1) toți antrenorii (include și AntrenorExtern dacă vrei)
    trainers = con.execute("""
        SELECT id, username,
               COALESCE(nume_complet, username) AS display_name,
               grupe
        FROM utilizatori
        WHERE LOWER(rol) = 'antrenor'
    """).fetchall()

    # 2) părinți (pentru copii)
    parents = con.execute("""
        SELECT username, email,
               COALESCE(nume_complet, username) AS display_name,
               copii
        FROM utilizatori
        WHERE LOWER(rol) = 'parinte'
    """).fetchall()

    # pre-parsăm copiii pentru toți părinții
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

    out = []  # <<< IMPORTANT: colectăm toți antrenorii aici (append), nu suprascriem

    for tr in trainers:
        # liste grupe ale antrenorului
        groups_raw = [g.strip() for g in (tr["grupe"] or "").split(",") if g.strip()]
        groups = [normalize_grupa(g) for g in groups_raw]
        groups = [g for g in groups if g]  # fără None/empty

        # map grupa -> listă copii
        groups_map = {g: [] for g in groups}

        # atașăm copiii părinților dacă grupa lor e în groups_map
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

        # construim structura finală pentru antrenorul curent
        grupe_list = [
            {"grupa": g, "copii": sorted(groups_map[g], key=lambda k: (str(k.get("nume") or "").lower()))}
            for g in sorted(groups_map.keys(), key=_group_sort_key)
        ]

        out.append({
            "antrenor": tr["username"],
            "antrenor_display": tr["display_name"],
            "grupe": grupe_list
        })

    # sortăm antrenorii alfabetic după display
    out.sort(key=lambda r: (r.get("antrenor_display") or r.get("antrenor") or "").lower())

    return jsonify({"status": "success", "data": out}), 200