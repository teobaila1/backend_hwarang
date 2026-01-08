# backend/users/elevi.py
import re
from flask import Blueprint, request, jsonify
from backend.config import get_conn

elevi_bp = Blueprint("elevi", __name__)


def _normalize(s):
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_columns(con, table_name: str):
    """
    Returnează lista coloanelor unui tabel.
    Funcționează pe PostgreSQL și SQLite.
    """
    # PostgreSQL
    try:
        rows = con.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
        """, (table_name,)).fetchall()

        if rows:
            return {r[0] for r in rows}
    except:
        pass

    # SQLite fallback
    try:
        info = con.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in info}
    except:
        return set()


@elevi_bp.post("/api/elevi/adauga")
def add_student():
    data = request.get_json(silent=True) or {}

    nume = _normalize(data.get("nume"))
    prenume = _normalize(data.get("prenume"))
    grupa = (data.get("grupa") or "").strip()
    varsta = (data.get("varsta") or "").strip()
    parinte_id = data.get("parinte_id")

    if not nume or not prenume or not parinte_id:
        return jsonify({
            "status": "error",
            "message": "Nume, prenume și parinte_id sunt obligatorii."
        }), 400

    con = get_conn()
    try:
        cols = _get_columns(con, "copii")

        fields = ["nume", "prenume", "parinte_id"]
        values = [nume, prenume, parinte_id]

        # coloane opționale dacă există
        if "grupa" in cols:
            fields.append("grupa")
            values.append(grupa)

        if "varsta" in cols:
            fields.append("varsta")
            values.append(varsta)

        placeholders = ", ".join(["%s"] * len(fields))
        sql = f"INSERT INTO copii ({', '.join(fields)}) VALUES ({placeholders})"

        cur = con.execute(sql, tuple(values))
        new_id = cur.lastrowid if hasattr(cur, "lastrowid") else None

        con.commit()

        return jsonify({
            "status": "success",
            "id": new_id,
            "message": "Elev adăugat."
        }), 201

    except Exception as e:
        con.rollback()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@elevi_bp.get("/api/elevi")
def get_students():
    con = get_conn()
    try:
        rows = con.execute("""
            SELECT id, nume, prenume, grupa, varsta, parinte_id
            FROM copii
            ORDER BY id DESC
        """).fetchall()

        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@elevi_bp.delete("/api/elevi/<int:elev_id>")
def delete_student(elev_id):
    con = get_conn()
    try:
        con.execute("DELETE FROM copii WHERE id = %s", (elev_id,))
        con.commit()
        return jsonify({"status": "success", "message": "Elev șters."})
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


# --- Adaugă la finalul fișierului elevi.py ---

@elevi_bp.get("/api/profil/sugestii_inscriere")
def sugestii_inscriere():
    username = request.args.get('username')

    if not username:
        return jsonify({"status": "error", "message": "Username lipsă"}), 400

    try:
        con = get_conn()

        # 1. Aflăm ID-ul și Rolul utilizatorului pe baza username-ului
        # Presupunem că tabela de useri se numește 'utilizatori'
        user = con.execute("SELECT id, rol, nume_complet FROM utilizatori WHERE username = %s", (username,)).fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Utilizator negăsit"}), 404

        user_id = user['id']
        rol = (user['rol'] or "").lower()
        nume_propriu = user['nume_complet'] or username
        lista_copii = []

        # 2. Dacă e Părinte sau Admin, luăm copiii din tabela 'copii'
        if rol in ['parinte', 'admin']:
            # Căutăm copiii asociați acestui cont (parinte_id)
            rows = con.execute("""
                SELECT nume, prenume, grupa 
                FROM copii 
                WHERE parinte_id = %s
            """, (user_id,)).fetchall()

            for r in rows:
                nume_full = f"{r['nume']} {r['prenume']}".strip()
                lista_copii.append({
                    "nume": nume_full,
                    "grupa": r.get('grupa', '')
                })

        return jsonify({
            "status": "success",
            "data": {
                "rol": rol,
                "nume_propriu": nume_propriu,
                "copii": lista_copii
            }
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500