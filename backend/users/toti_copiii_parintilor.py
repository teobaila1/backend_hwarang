# backend/users/toti_copiii_parintilor.py
import json
import re
import uuid
from flask import Blueprint, jsonify, request
from ..config import get_conn

toti_copiii_parintilor_bp = Blueprint('copiii_parintilor', __name__)


def _safe_load_list(s):
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _normalize_grupa(value: str):
    """Acceptă '7', 'Grupa7', 'Grupa 7' și întoarce 'Grupa 7'."""
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r'^\s*(?:grupa\s*)?(\d+)\s*$', s, re.IGNORECASE)
    return f"Grupa {m.group(1)}" if m else s


def _is_admin(con, username):
    r = con.execute("SELECT rol FROM utilizatori WHERE username=%s", (username,)).fetchone()
    return bool(r and str(r["rol"]).lower() == "admin")


# ---------------- GET toți copiii (CU AUTO-REPARARE ID-uri) ----------------
@toti_copiii_parintilor_bp.get("/api/toti_copiii")
def toti_copiii():
    try:
        con = get_conn()
        rows = con.execute("""
          SELECT
            id,
            username,
            email,
            copii,
            nume_complet,
            COALESCE(nume_complet, username) AS display_name
          FROM utilizatori
          WHERE LOWER(rol) IN ('parinte', 'admin') AND copii IS NOT NULL
        """).fetchall()

        rezultate = []

        for r in rows:
            user_id = r["id"]
            raw_copii = r["copii"]
            lista_copii = _safe_load_list(raw_copii)

            # --- LOGICA DE AUTO-VINDECARE (SELF-HEALING) ---
            # Verificăm dacă există copii fără ID și le generăm unul acum
            needs_update = False
            for copil in lista_copii:
                # Dacă e dicționar și nu are cheia 'id' sau e goală
                if isinstance(copil, dict) and not copil.get("id"):
                    copil["id"] = uuid.uuid4().hex
                    needs_update = True

            # Dacă am găsit copii fără ID, salvăm lista corectată înapoi în DB
            if needs_update:
                try:
                    con.execute(
                        "UPDATE utilizatori SET copii = %s WHERE id = %s",
                        (json.dumps(lista_copii, ensure_ascii=False), user_id)
                    )
                    con.commit()  # Salvăm reparația permanent
                    print(f"DEBUG: Am generat ID-uri lipsă pentru userul {r['username']}")
                except Exception as e:
                    print(f"Eroare la auto-vindecare ID-uri: {e}")
            # ------------------------------------------------

            rezultate.append({
                "parinte": {
                    "username": r["username"],
                    "email": r["email"],
                    "nume_complet": r["nume_complet"],
                    "display": r["display_name"],
                },
                "copii": lista_copii
            })

        return jsonify({"status": "success", "date": rezultate})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------- POST adaugă copil ----------------
@toti_copiii_parintilor_bp.post("/api/adauga_copil")
def adauga_copil():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    nume = (data.get("nume") or "").strip()
    varsta = data.get("varsta")
    grupa = _normalize_grupa(data.get("grupa"))
    gen = (data.get("gen") or "").strip()  # opțional

    if not username or not nume or varsta is None or not grupa:
        return jsonify({"status": "error", "message": "Date incomplete"}), 400

    if isinstance(varsta, str) and varsta.isdigit():
        varsta = int(varsta)

    try:
        con = get_conn()
        row = con.execute(
            "SELECT copii FROM utilizatori WHERE username = %s AND LOWER(rol) IN ('parinte', 'admin')",
            (username,)
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Utilizator inexistent sau nu este Părinte"}), 404

        lista = _safe_load_list(row["copii"])
        copil_nou = {
            "id": uuid.uuid4().hex,  # Asigurăm ID la adăugare
            "nume": nume,
            "varsta": varsta,
            "grupa": grupa,
            "gen": gen or None
        }
        lista.append(copil_nou)

        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE username = %s",
            (json.dumps(lista, ensure_ascii=False), username)
        )
        con.commit()
        return jsonify({"status": "success", "message": "Copil adăugat cu succes"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------- ADMIN: PATCH copil ----------------
@toti_copiii_parintilor_bp.patch("/api/admin/copii/<child_id>")
def admin_update_child(child_id):
    # Verificăm să nu fie undefined din start
    if not child_id or child_id == "undefined":
        return jsonify(
            {"status": "error", "message": "ID copil invalid. Dă refresh la pagină pentru a repara datele."}), 400

    data = request.get_json(silent=True) or {}
    admin_username = (data.get("admin_username") or "").strip()
    parent_username = (data.get("parent_username") or "").strip()

    if not admin_username or not parent_username:
        return jsonify({"status": "error", "message": "Lipsește admin_username sau parent_username."}), 400

    fields = {}
    if "nume" in data:    fields["nume"] = (data["nume"] or "").strip()
    if "gen" in data:     fields["gen"] = (data["gen"] or None)
    if "grupa" in data:   fields["grupa"] = _normalize_grupa(data["grupa"])
    if "varsta" in data:
        try:
            fields["varsta"] = int(data["varsta"])
        except:
            return jsonify({"status": "error", "message": "Vârsta trebuie să fie număr."}), 400

    try:
        con = get_conn()
        if not _is_admin(con, admin_username):
            return jsonify({"status": "error", "message": "Doar adminul are voie."}), 403

        r = con.execute(
            "SELECT copii FROM utilizatori WHERE username=%s AND LOWER(rol) IN ('parinte', 'admin')",
            (parent_username,)
        ).fetchone()
        if not r:
            return jsonify({"status": "error", "message": "Părinte inexistent."}), 404

        copii = _safe_load_list(r["copii"])

        # Căutăm copilul după ID
        idx = next((i for i, c in enumerate(copii) if str(c.get("id")) == str(child_id)), None)

        if idx is None:
            return jsonify({"status": "error", "message": f"Copil cu ID {child_id} nu a fost găsit."}), 404

        copii[idx].update(fields)

        con.execute(
            "UPDATE utilizatori SET copii=%s WHERE username=%s",
            (json.dumps(copii, ensure_ascii=False), parent_username)
        )
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------- ADMIN: DELETE copil ----------------
@toti_copiii_parintilor_bp.delete("/api/admin/copii/<child_id>")
def admin_delete_child(child_id):
    data = request.get_json(silent=True) or {}
    admin_username = (data.get("admin_username") or "").strip()
    parent_username = (data.get("parent_username") or "").strip()
    if not admin_username or not parent_username:
        return jsonify({"status": "error", "message": "Lipsește admin_username sau parent_username."}), 400

    try:
        con = get_conn()
        if not _is_admin(con, admin_username):
            return jsonify({"status": "error", "message": "Doar adminul are voie."}), 403

        r = con.execute(
            "SELECT copii FROM utilizatori WHERE username=%s AND LOWER(rol) IN ('parinte', 'admin')",
            (parent_username,)
        ).fetchone()
        if not r:
            return jsonify({"status": "error", "message": "Părinte inexistent."}), 404

        copii = _safe_load_list(r["copii"])
        new_list = [c for c in copii if str(c.get("id")) != str(child_id)]

        if len(new_list) == len(copii):
            return jsonify({"status": "error", "message": "Copil inexistent."}), 404

        con.execute(
            "UPDATE utilizatori SET copii=%s WHERE username=%s",
            (json.dumps(new_list, ensure_ascii=False), parent_username)
        )
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------- ADMIN: PATCH părinte ----------------
def _ensure_column(con, table, column, sql_type="TEXT"):
    exists = False
    try:
        row = con.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s LIMIT 1
        """, (table, column)).fetchone()
        exists = bool(row)
    except Exception:
        try:
            info = con.execute(f"PRAGMA table_info({table})").fetchall()
            cols = {r[1] for r in info}
            exists = column in cols
        except Exception:
            exists = False

    if not exists:
        con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}')
        con.commit()


@toti_copiii_parintilor_bp.patch("/api/admin/parinte/<parent_username>")
def admin_update_parent(parent_username):
    data = request.get_json(silent=True) or {}
    admin_username = (data.get("admin_username") or "").strip()
    if not admin_username:
        return jsonify({"status": "error", "message": "Lipsește admin_username."}), 400

    new_username = (data.get("new_username") or "").strip() or parent_username
    email = (data.get("email") or None)
    nume_complet = (data.get("nume_complet") or "").strip() or None

    try:
        con = get_conn()
        if not _is_admin(con, admin_username):
            return jsonify({"status": "error", "message": "Doar adminul are voie."}), 403

        _ensure_column(con, "utilizatori", "nume_complet", "TEXT")

        if new_username.lower() != parent_username.lower():
            exists = con.execute(
                "SELECT 1 FROM utilizatori WHERE LOWER(username)=LOWER(%s)",
                (new_username,)
            ).fetchone()
            if exists:
                return jsonify({"status": "error", "message": "Username deja folosit."}), 409

        row = con.execute(
            "SELECT id FROM utilizatori WHERE username=%s AND LOWER(rol) IN ('parinte', 'admin')",
            (parent_username,)
        ).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Părinte inexistent."}), 404

        fields, values = [], []
        fields.append("username = %s");
        values.append(new_username)
        fields.append("email = %s");
        values.append(email)
        fields.append("nume_complet = %s");
        values.append(nume_complet)

        values.append(row["id"])
        con.execute(f"UPDATE utilizatori SET {', '.join(fields)} WHERE id = %s", values)
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------- ADMIN: DELETE părinte ----------------
@toti_copiii_parintilor_bp.delete("/api/admin/parinte/<parent_username>")
def admin_delete_parent(parent_username):
    data = request.get_json(silent=True) or {}
    admin_username = (data.get("admin_username") or "").strip()
    if not admin_username:
        return jsonify({"status": "error", "message": "Lipsește admin_username."}), 400

    try:
        con = get_conn()
        if not _is_admin(con, admin_username):
            return jsonify({"status": "error", "message": "Doar adminul are voie."}), 403

        cur = con.execute(
            "DELETE FROM utilizatori WHERE username=%s AND LOWER(rol) IN ('parinte', 'admin')",
            (parent_username,)
        )
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Părinte inexistent."}), 404
        con.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500