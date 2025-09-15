# backend/users/antrenor_dashboard_copii_parinti.py
import re
import uuid
import json
from flask import request, jsonify, Blueprint
from ..config import get_conn, DB_PATH  # ✅ sursă unică pentru DB

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


def ensure_child_ids_and_normalize(children):
    """Adaugă id lipsă, transformă varsta în int, normalizează grupa."""
    changed = False
    for c in children:
        if "id" not in c or not c["id"]:
            c["id"] = uuid.uuid4().hex
            changed = True
        # varsta -> int dacă e string numeric
        if "varsta" in c and isinstance(c["varsta"], str) and c["varsta"].isdigit():
            c["varsta"] = int(c["varsta"])
            changed = True
        # grupa -> 'Grupa X' unde e cazul
        if "grupa" in c:
            ng = _normalize_grupa(c["grupa"])
            if ng != c["grupa"]:
                c["grupa"] = ng
                changed = True
    return changed, children
# -----------------------------





@antrenor_dashboard_copii_parinti_bp.post("/api/antrenor_dashboard_data")
def antrenor_dashboard_data():
    """
    Răspuns: listă de rânduri de forma:
      { grupa: "Grupa X", parinte: {id,username,email,display} | None, copii: [...] }
    - filtrează doar grupele pe care le are antrenorul
    - include UN rând placeholder pentru fiecare grupă permisă (copii=[], parinte=None)
    """
    data = request.get_json(silent=True) or {}
    trainer_username = (data.get("username") or "").strip()
    if not trainer_username:
        return jsonify({"status": "error", "message": "Lipsă username antrenor."}), 400

    con = get_conn()
    try:
        # 1) Grupele antrenorului -> set normalizat "Grupa N"
        tr = con.execute(
            "SELECT grupe FROM utilizatori WHERE LOWER(rol)='antrenor' AND username = ?",
            (trainer_username,)
        ).fetchone()
        if not tr:
            return jsonify({"status": "success", "date": []}), 200

        allowed = set()
        for raw in (tr["grupe"] or "").split(","):
            ng = _normalize_grupa(raw)
            if ng:
                allowed.add(ng)

        if not allowed:
            # antrenor fără grupe setate
            return jsonify({"status": "success", "date": []}), 200

        # 2) Începem cu câte un placeholder pentru fiecare grupă permisă
        results = [{"grupa": g, "parinte": None, "copii": []} for g in allowed]

        # 3) Părinții și copiii lor
        rows = con.execute("""
            SELECT
                id,
                username,
                email,
                copii,
                COALESCE(nume_complet, username) AS display_name
            FROM utilizatori
            WHERE LOWER(rol) = 'parinte'
        """).fetchall()

        for r in rows:
            children = _safe_load_children(r["copii"])
            if not children:
                continue

            # copii grupați pe grupă, ținem doar grupele din allowed
            by_group = {}
            for c in children:
                g = _normalize_grupa(c.get("grupa")) or "Fără grupă"
                if g not in allowed:
                    continue
                by_group.setdefault(g, []).append({
                    "id": c.get("id"),
                    "nume": c.get("nume"),
                    "varsta": c.get("varsta"),
                    "gen": c.get("gen"),
                    "grupa": g,
                })

            if not by_group:
                continue

            # pentru fiecare grupă permisă la care am copii -> adaug un rând real
            for gname, kids in by_group.items():
                results.append({
                    "grupa": gname,
                    "parinte": {
                        "id": r["id"],
                        "username": r["username"] or "—",
                        "email": r["email"],
                        "display": r["display_name"],
                    },
                    "copii": kids
                })

        # 4) sortare stabilă: după numărul grupei, apoi după numele părintelui
        def group_key(name: str):
            import re
            m = re.search(r"(\d+)", name or "")
            return (int(m.group(1)) if m else 9999, (name or "").lower())

        results.sort(key=lambda x: (group_key(x["grupa"]),
                                    (x["parinte"] or {}).get("display", (x["parinte"] or {}).get("username", ""))).__str__())
        return jsonify({"status": "success", "date": results}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500




@antrenor_dashboard_copii_parinti_bp.route("/api/copiii_mei", methods=["POST"])
def copiii_mei():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Lipsă username"}), 400

    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute(
            "SELECT copii FROM utilizatori WHERE username = ? AND LOWER(rol) = 'parinte'",
            (username,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Părinte inexistent sau fără copii"}), 404

        copii = []
        if row["copii"]:
            try:
                copii = json.loads(row["copii"])
            except Exception:
                copii = []

        # ca să fim consecvenți, normalizăm și aici și adăugăm id-uri dacă lipsesc
        changed, copii = ensure_child_ids_and_normalize(copii)
        if changed:
            cur.execute(
                "UPDATE utilizatori SET copii = ? WHERE username = ?",
                (json.dumps(copii, ensure_ascii=False), username)
            )
            con.commit()

        return jsonify({"status": "success", "copii": copii})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
