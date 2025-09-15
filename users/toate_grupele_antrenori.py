# backend/users/toate_grupele_antrenori.py
import json
import re
from flask import Blueprint, jsonify
from ..config import get_conn, DB_PATH

toate_grupele_antrenori_bp = Blueprint('toate_grupele_antrenori', __name__)

def normalize_grupa(value):
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r'^\s*(?:grupa\s*)?(\d+)\s*$', s, re.IGNORECASE)
    return f"Grupa {m.group(1)}" if m else s

def _ensure_child_ids_and_normalize(children):
    """Adaugă id dacă lipsește și normalizează grupa; întoarce (changed, children)."""
    import uuid
    changed = False
    for c in children or []:
        if not c.get("id"):
            c["id"] = uuid.uuid4().hex
            changed = True
        if "grupa" in c:
            ng = normalize_grupa(c["grupa"])
            if ng != c["grupa"]:
                c["grupa"] = ng
                changed = True
        # varsta întotdeauna int dacă e posibil (fără să stricăm dacă nu e numeric)
        if "varsta" in c and isinstance(c["varsta"], str) and c["varsta"].isdigit():
            c["varsta"] = int(c["varsta"])
            changed = True
    return changed, children

@toate_grupele_antrenori_bp.get("/api/toate_grupele_antrenori")
def toate_grupele_antrenori():
    try:
        con = get_conn()

        # 1) Toți antrenorii cu grupele lor
        antrenori_rows = con.execute(
            """
            SELECT
              username,
              COALESCE(nume_complet, username) AS display_name,
              grupe
            FROM utilizatori
            WHERE LOWER(rol) = 'antrenor'
              AND grupe IS NOT NULL
            """
        ).fetchall()

        # 2) Toți părinții + copii (cu id-uri asigurate)
        parinti_rows = con.execute(
            "SELECT id, username, email, copii FROM utilizatori WHERE LOWER(rol) = 'parinte'"
        ).fetchall()

        parinti_parsati = []
        for r in parinti_rows:
            copii_list = []
            if r["copii"]:
                try:
                    copii_list = json.loads(r["copii"])
                except Exception:
                    copii_list = []
            changed, copii_list = _ensure_child_ids_and_normalize(copii_list)
            if changed:
                con.execute(
                    "UPDATE utilizatori SET copii = ? WHERE id = ?",
                    (json.dumps(copii_list, ensure_ascii=False), r["id"])
                )
                con.commit()

            parinti_parsati.append({
                "id": r["id"],
                "username": r["username"],
                "email": r["email"],
                "copii": copii_list
            })

        rezultat_final = []

        for a in antrenori_rows:
            antrenor = a["username"]
            antrenor_display = a["display_name"]
            grupe_raw = (a["grupe"] or "")
            grupe_norm = [normalize_grupa(g) for g in grupe_raw.split(",") if g.strip()]

            grupe_result = []
            for grupa in grupe_norm:
                for par in parinti_parsati:
                    # copii părinte în grupa curentă
                    copii_din_grupa = []
                    for c in par["copii"]:
                        if normalize_grupa(c.get("grupa")) == grupa:
                            copii_din_grupa.append({
                                "id": c.get("id"),                # <<— NECESAR pt edit/delete
                                "nume": c.get("nume"),
                                "varsta": c.get("varsta"),
                                "gen": c.get("gen"),
                                "grupa": grupa
                            })

                    if copii_din_grupa:
                        grupe_result.append({
                            "grupa": grupa,
                            "copii": copii_din_grupa,
                            "parinte": {
                                "id": par["id"],
                                "username": par["username"],
                                "email": par["email"]
                            }
                        })

        rezultat_final.append({
            "antrenor": antrenor,
            "antrenor_display": antrenor_display,  # 👈 adăugat
            "grupe": grupe_result
        })

        return jsonify({"status": "success", "data": rezultat_final})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
