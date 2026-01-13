# backend/users/toti_copiii_parintilor.py
import json
import re
import uuid
from flask import Blueprint, jsonify, request

from ..accounts.decorators import admin_required, token_required
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
# --- RUTĂ: Admin vede toți copiii (pentru AdminTotiCopiiiSiParintii.jsx) ---
@toti_copiii_parintilor_bp.get("/api/toti_copiii")
@token_required
@admin_required
def toti_copiii():
    try:
        con = get_conn()
        # Luăm doar userii care au ceva în coloana 'copii'
        rows = con.execute("""
            SELECT id, username, email, nume_complet, copii 
            FROM utilizatori 
            WHERE copii IS NOT NULL
        """).fetchall()

        rezultat = []
        for r in rows:
            copii_list = _safe_load_list(r["copii"])

            # Curățăm lista (eliminăm intrările goale dacă există)
            copii_curati = [c for c in copii_list if isinstance(c, dict) and c.get("nume")]

            if copii_curati:
                rezultat.append({
                    "parinte": {
                        "id": r["id"],
                        "username": r["username"],
                        "email": r["email"],
                        "nume_complet": r["nume_complet"]
                    },
                    "copii": copii_curati
                })

        return jsonify({"status": "success", "date": rezultat}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ---------------- POST adaugă copil ----------------
# --- RUTĂ: Părintele își adaugă un copil ---
@toti_copiii_parintilor_bp.post("/api/adauga_copil")
@token_required
def adauga_copil():
    data = request.get_json(silent=True) or {}

    # 1. Preluăm datele din Frontend
    # Frontend-ul trimite "parinte_username" (din localStorage)
    target_username = data.get("parinte_username")

    # Dacă nu vine username-ul, încercăm să îl luăm din token (pentru siguranță)
    if not target_username and hasattr(request, 'user_data'):
        target_username = request.user_data.get('username')

    nume = (data.get("nume") or "").strip()
    varsta = data.get("varsta")
    grupa = (data.get("grupa") or "").strip()
    gen = data.get("gen")

    # Validări simple
    if not target_username:
        return jsonify({"status": "error", "message": "Nu s-a putut identifica părintele."}), 400
    if not nume:
        return jsonify({"status": "error", "message": "Numele copilului este obligatoriu."}), 400

    try:
        con = get_conn()

        # 2. Căutăm părintele și luăm lista actuală de copii
        row = con.execute(
            "SELECT id, copii FROM utilizatori WHERE username = %s",
            (target_username,)
        ).fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Contul de părinte nu există."}), 404

        parent_id = row["id"]
        # Decodăm JSON-ul existent (sau listă goală dacă e NULL)
        lista_copii = _safe_load_list(row["copii"])

        # 3. Creăm obiectul copil nou
        nou_copil = {
            "id": uuid.uuid4().hex,  # Generăm un ID unic pentru copil
            "nume": nume,
            "varsta": varsta,
            "gen": gen,
            "grupa": _normalize_grupa(grupa)
        }

        # Îl adăugăm la listă
        lista_copii.append(nou_copil)

        # 4. Salvăm înapoi în baza de date
        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(lista_copii, ensure_ascii=False), parent_id)
        )
        con.commit()

        return jsonify({"status": "success", "message": "Copil adăugat cu succes!"}), 200

    except Exception as e:
        print(f"Eroare adauga_copil: {e}")  # Ajută la debug în consolă
        return jsonify({"status": "error", "message": "Eroare server: " + str(e)}), 500


# ---------------- ADMIN: PATCH copil ----------------
# --- RUTĂ: Admin editează un copil specific ---
@toti_copiii_parintilor_bp.patch("/api/admin/copii/<child_id>")
@token_required
@admin_required
def admin_update_child(child_id):
    data = request.get_json(silent=True) or {}

    # Avem nevoie de username-ul părintelui pentru a ști în ce rând din DB să căutăm
    parent_username = data.get("parent_username")

    # Datele noi
    nume = data.get("nume")
    varsta = data.get("varsta")
    gen = data.get("gen")
    grupa = data.get("grupa")

    if not parent_username:
        return jsonify({"status": "error", "message": "Lipsește username-ul părintelui."}), 400

    try:
        con = get_conn()
        # Găsim părintele
        row = con.execute(
            "SELECT id, copii FROM utilizatori WHERE username = %s",
            (parent_username,)
        ).fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Părintele nu a fost găsit."}), 404

        copii_list = _safe_load_list(row["copii"])
        found = False

        # Căutăm copilul în lista părintelui
        for c in copii_list:
            if c.get("id") == child_id:
                if nume is not None: c["nume"] = nume
                if varsta is not None: c["varsta"] = varsta
                if gen is not None: c["gen"] = gen
                if grupa is not None: c["grupa"] = _normalize_grupa(grupa)
                found = True
                break

        if not found:
            return jsonify({"status": "error", "message": "Copilul nu a fost găsit în lista părintelui."}), 404

        # Salvăm
        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(copii_list, ensure_ascii=False), row["id"])
        )
        con.commit()

        return jsonify({"status": "success", "message": "Copil actualizat."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ---------------- ADMIN: DELETE copil ----------------
# --- RUTĂ: Admin șterge un copil specific ---
@toti_copiii_parintilor_bp.delete("/api/admin/copii/<child_id>")
@token_required
@admin_required
def admin_delete_child(child_id):
    data = request.get_json(silent=True) or {}
    parent_username = data.get("parent_username")

    if not parent_username:
        return jsonify({"status": "error", "message": "Lipsește username-ul părintelui."}), 400

    try:
        con = get_conn()
        row = con.execute("SELECT id, copii FROM utilizatori WHERE username=%s", (parent_username,)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Părinte inexistent."}), 404

        copii_list = _safe_load_list(row["copii"])

        # Filtrăm lista ca să eliminăm copilul cu ID-ul respectiv
        noua_lista = [c for c in copii_list if c.get("id") != child_id]

        if len(noua_lista) == len(copii_list):
            return jsonify({"status": "error", "message": "Copilul nu a fost găsit."}), 404

        con.execute(
            "UPDATE utilizatori SET copii = %s WHERE id = %s",
            (json.dumps(noua_lista, ensure_ascii=False), row["id"])
        )
        con.commit()

        return jsonify({"status": "success", "message": "Copil șters."}), 200

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
@token_required
@admin_required
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
# --- RUTĂ: Admin șterge complet un părinte ---
@toti_copiii_parintilor_bp.delete("/api/admin/parinte/<parent_username>")
@token_required
@admin_required
def admin_delete_parent(parent_username):
    try:
        con = get_conn()
        # Ștergem doar dacă rolul e parinte (sau admin, după caz, dar ai grijă aici)
        cur = con.execute(
            "DELETE FROM utilizatori WHERE username=%s",
            (parent_username,)
        )
        if cur.rowcount == 0:
            return jsonify({"status": "error", "message": "Utilizatorul nu există."}), 404

        con.commit()
        return jsonify({"status": "success", "message": "Părinte șters."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500