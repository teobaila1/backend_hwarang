# backend/users/antrenor_dashboard_copii_parinti.py
import re
import uuid
import json
from flask import request, jsonify, Blueprint

from ..accounts.decorators import token_required
from ..config import get_conn  # ✅ sursă unică pentru DB

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
    """
    Verifică fiecare copil. Dacă nu are ID, îi generează unul.
    Normalizează grupa și vârsta.
    Returnează (True, lista_noua) dacă s-a modificat ceva, altfel (False, lista_veche).
    """
    changed = False
    for c in children:
        # 1. GENERARE ID DACĂ LIPSEȘTE (Asta rezolvă problema cu butonul gri)
        if "id" not in c or not c["id"]:
            c["id"] = uuid.uuid4().hex
            changed = True

        # 2. Vârsta număr
        if "varsta" in c and isinstance(c["varsta"], str) and c["varsta"].isdigit():
            c["varsta"] = int(c["varsta"])
            changed = True

        # 3. Normalizare grupă
        if "grupa" in c:
            ng = _normalize_grupa(c["grupa"])
            if ng != c["grupa"]:
                c["grupa"] = ng
                changed = True
    return changed, children


# -----------------------------


@antrenor_dashboard_copii_parinti_bp.post("/api/antrenor_dashboard_data")
@token_required
def antrenor_dashboard_data():
    """
    Returnează datele pentru dashboard și REPARĂ automat copiii fără ID.
    """
    data = request.get_json(silent=True) or {}
    trainer_username = (data.get("username") or "").strip()
    if not trainer_username:
        return jsonify({"status": "error", "message": "Lipsă username antrenor."}), 400

    con = get_conn()
    try:
        # 1) Aflăm ce grupe are voie să vadă acest user (Antrenor sau Admin)
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

        # 2) Inițializăm structura
        results = [{"grupa": g, "parinte": None, "copii": []} for g in allowed]

        # 3) Luăm toți părinții/adminii care au copii
        rows = con.execute("""
            SELECT
                id,
                username,
                email,
                copii,
                COALESCE(nume_complet, username) AS display_name
            FROM utilizatori
            WHERE LOWER(rol) IN ('parinte', 'admin') AND copii IS NOT NULL
        """).fetchall()

        # --- AICI ESTE FIX-UL ---
        # Iterăm prin toți părinții. Dacă găsim copii fără ID, îi reparăm și salvăm în DB.

        for r in rows:
            children = _safe_load_children(r["copii"])
            if not children:
                continue

            # Apelează funcția de reparare
            was_changed, fixed_children = ensure_child_ids_and_normalize(children)

            if was_changed:
                # Dăm UPDATE în baza de date imediat, ca să fie permanent
                con.execute(
                    "UPDATE utilizatori SET copii = %s WHERE id = %s",
                    (json.dumps(fixed_children, ensure_ascii=False), r["id"])
                )
                con.commit()  # Salvăm modificarea
                children = fixed_children  # Folosim lista reparată pentru afișare

            # --- FILTRARE PENTRU DASHBOARD ---
            # Acum copiii au sigur ID-uri
            by_group = {}
            for c in children:
                g = _normalize_grupa(c.get("grupa")) or "Fără grupă"
                if g not in allowed:
                    continue
                by_group.setdefault(g, []).append({
                    "id": c.get("id"),  # Acum există sigur!
                    "nume": c.get("nume"),
                    "varsta": c.get("varsta"),
                    "gen": c.get("gen"),
                    "grupa": g,
                })

            if not by_group:
                continue

            # Construim răspunsul
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

        # 4) Sortare
        def group_key(name: str):
            import re
            m = re.search(r"(\d+)", name or "")
            return (int(m.group(1)) if m else 9999, (name or "").lower())

        results.sort(key=lambda x: (group_key(x["grupa"]),
                                    (x["parinte"] or {}).get("display",
                                                             (x["parinte"] or {}).get("username", ""))).__str__())

        return jsonify({"status": "success", "date": results}), 200

    except Exception as e:
        print(f"Eroare dashboard: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@antrenor_dashboard_copii_parinti_bp.route("/api/copiii_mei", methods=["POST"])
@token_required
def copiii_mei():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username:
        return jsonify({"status": "error", "message": "Lipsă username"}), 400

    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute(
            "SELECT id, copii FROM utilizatori WHERE username = %s AND LOWER(rol) IN ('parinte', 'admin')",
            (username,)
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Părinte inexistent sau fără copii"}), 404

        copii = _safe_load_children(row["copii"])

        # Auto-repair și aici, just in case
        changed, copii = ensure_child_ids_and_normalize(copii)
        if changed:
            cur.execute(
                "UPDATE utilizatori SET copii = %s WHERE id = %s",
                (json.dumps(copii, ensure_ascii=False), row["id"])
            )
            con.commit()

        return jsonify({"status": "success", "copii": copii})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500