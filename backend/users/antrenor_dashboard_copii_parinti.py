import re
import uuid
import json
from datetime import datetime
from flask import request, jsonify, Blueprint

from ..accounts.decorators import token_required
from ..config import get_conn

antrenor_dashboard_copii_parinti_bp = Blueprint("antrenor_dashboard_copii_parinti", __name__)


def _normalize_grupa(value):
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r'^\s*(?:grupa\s*)?(\d+)\s*$', s, re.IGNORECASE)
    return f"Grupa {m.group(1)}" if m else s


def _safe_load_children(copii_json):
    try:
        v = json.loads(copii_json or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _calculate_age(dob):
    if not dob:
        return 0
    try:
        if isinstance(dob, str):
            birth_date = datetime.strptime(dob, "%Y-%m-%d")
        else:
            birth_date = dob
        today = datetime.now()
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    except Exception:
        return 0


def ensure_child_ids_and_normalize(children):
    changed = False
    for c in children:
        if "id" not in c or not c["id"]:
            c["id"] = uuid.uuid4().hex
            changed = True
        if "varsta" in c and isinstance(c["varsta"], str) and c["varsta"].isdigit():
            c["varsta"] = int(c["varsta"])
            changed = True
        if "grupa" in c:
            ng = _normalize_grupa(c["grupa"])
            if ng != c["grupa"]:
                c["grupa"] = ng
                changed = True
    return changed, children


@antrenor_dashboard_copii_parinti_bp.post("/api/antrenor_dashboard_data")
@token_required
def antrenor_dashboard_data():
    data = request.get_json(silent=True) or {}
    trainer_username = (data.get("username") or "").strip()
    if not trainer_username:
        return jsonify({"status": "error", "message": "Lipsă username antrenor."}), 400

    con = get_conn()
    try:
        # 1. Aflăm grupele antrenorului
        tr = con.execute("""
            SELECT grupe FROM utilizatori 
            WHERE (LOWER(rol)='antrenor' OR LOWER(rol)='admin') 
              AND username = %s
        """, (trainer_username,)).fetchone()

        if not tr:
            return jsonify({"status": "success", "date": []}), 200

        allowed = set()
        for raw in (tr["grupe"] or "").split(","):
            ng = _normalize_grupa(raw)
            if ng:
                allowed.add(ng)

        if not allowed:
            return jsonify({"status": "success", "date": []}), 200

        results = [{"grupa": g, "parinte": None, "copii": []} for g in allowed]

        # --- A. Procesăm PĂRINȚII și copiii lor ---
        parents = con.execute("""
            SELECT id, username, email, copii, COALESCE(nume_complet, username) AS display_name
            FROM utilizatori
            WHERE LOWER(rol) IN ('parinte', 'admin') AND copii IS NOT NULL
        """).fetchall()

        for r in parents:
            children = _safe_load_children(r["copii"])
            if not children: continue

            was_changed, fixed_children = ensure_child_ids_and_normalize(children)
            if was_changed:
                con.execute("UPDATE utilizatori SET copii = %s WHERE id = %s",
                            (json.dumps(fixed_children, ensure_ascii=False), r["id"]))
                con.commit()
                children = fixed_children

            by_group = {}
            for c in children:
                g = _normalize_grupa(c.get("grupa"))
                if g in allowed:
                    by_group.setdefault(g, []).append({
                        "id": c.get("id"),
                        "nume": c.get("nume"),
                        "varsta": c.get("varsta"),
                        "gen": c.get("gen"),
                        "grupa": g,
                    })

            for gname, kids in by_group.items():
                results.append({
                    "grupa": gname,
                    "parinte": {
                        "id": r["id"],
                        "username": r["username"],
                        "email": r["email"],
                        "display": r["display_name"],
                    },
                    "copii": kids
                })

        # --- B. Procesăm SPORTIVII INDEPENDENȚI (ACUM E ÎN AFARA BUCLEI DE PĂRINȚI) ---
        sportivi = con.execute("""
            SELECT id, username, email, nume_complet, grupe, data_nasterii, gen
            FROM utilizatori
            WHERE LOWER(rol) = 'sportiv'
        """).fetchall()

        for s in sportivi:
            g_raw = s["grupe"]
            if not g_raw: continue

            varsta_reala = _calculate_age(s["data_nasterii"])
            gen_real = s["gen"] if s["gen"] else "—"

            sportiv_groups = [_normalize_grupa(x) for x in g_raw.split(",")]

            for g_s in sportiv_groups:
                if g_s in allowed:
                    display_name = s["nume_complet"] or s["username"]

                    virtual_child = {
                        "id": str(s["id"]),
                        "nume": display_name,
                        "varsta": varsta_reala,
                        "gen": gen_real,
                        "grupa": g_s
                    }

                    results.append({
                        "grupa": g_s,
                        "parinte": {
                            "id": s["id"],
                            "username": s["username"],
                            "email": s["email"],
                            "display": f"{display_name} (Sportiv)"
                        },
                        "copii": [virtual_child]
                    })

        # Sortare
        def group_key(name: str):
            import re
            m = re.search(r"(\d+)", name or "")
            return (int(m.group(1)) if m else 9999, (name or "").lower())

        results.sort(key=lambda x: (group_key(x["grupa"]), (x["parinte"] or {}).get("display", "")))

        return jsonify({"status": "success", "date": results}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@antrenor_dashboard_copii_parinti_bp.route("/api/copiii_mei", methods=["POST"])
@token_required
def copiii_mei():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username: return jsonify({"status": "error"}), 400
    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute("SELECT id, copii FROM utilizatori WHERE username=%s AND LOWER(rol) IN ('parinte', 'admin')",
                    (username,))
        row = cur.fetchone()
        if not row: return jsonify({"status": "error"}), 404
        copii = _safe_load_children(row["copii"])
        changed, copii = ensure_child_ids_and_normalize(copii)
        if changed:
            cur.execute("UPDATE utilizatori SET copii=%s WHERE id=%s",
                        (json.dumps(copii, ensure_ascii=False), row["id"]))
            con.commit()
        return jsonify({"status": "success", "copii": copii})
    except Exception as e:
        return jsonify({"status": "error"}), 500