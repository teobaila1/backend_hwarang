# backend/users/elevi.py
import json
import re
import uuid
from flask import Blueprint, request, jsonify
from backend.config import get_conn

elevi_bp = Blueprint("elevi", __name__)


def _normalize(s):
    s = (s or "").strip()
    return re.sub(r"\s+", " ", s)


def _safe_load_list(s):
    if not s:
        return []
    try:
        if isinstance(s, list): return s
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except:
        return []


# --- 1. GET: Returnează toți elevii (din JSON-urile părinților) ---
@elevi_bp.get("/api/elevi")
def get_students():
    con = get_conn()
    try:
        # Selectăm toți userii care au copii
        rows = con.execute("""
            SELECT id, nume_complet, username, copii 
            FROM utilizatori 
            WHERE copii IS NOT NULL AND json_array_length(copii::json) > 0
        """).fetchall()

        toti_elevii = []
        for r in rows:
            parinte_nume = r["nume_complet"] or r["username"]
            parinte_id = r["id"]
            copii_list = _safe_load_list(r["copii"])

            for copil in copii_list:
                # Adăugăm info despre părinte la fiecare copil pentru afișare
                copil["parinte_id"] = parinte_id
                copil["parinte_nume"] = parinte_nume
                toti_elevii.append(copil)

        return jsonify(toti_elevii)
    except Exception as e:
        print(f"Eroare GET elevi: {e}")
        return jsonify([])  # Returnăm listă goală în caz de eroare, să nu crape frontend-ul


# --- 2. POST: Adaugă un elev (Actualizează JSON-ul părintelui) ---
@elevi_bp.post("/api/elevi")  # <--- FIX: Ruta este acum /api/elevi (nu /adauga)
def add_student():
    data = request.get_json(silent=True) or {}

    # Datele din formularul modal
    nume_elev = _normalize(data.get("nume"))  # Frontend trimite "nume" (pentru elev)
    varsta = data.get("varsta")
    gen = data.get("gen")
    grupa = data.get("grupa")

    # Numele părintelui este opțional în formular, dar critic pentru backend
    nume_parinte = _normalize(data.get("nume_parinte"))

    if not nume_elev:
        return jsonify({"status": "error", "message": "Numele elevului este obligatoriu."}), 400

    con = get_conn()
    try:
        parent_id = None
        current_copii = []

        # A. Încercăm să găsim părintele dacă s-a introdus un nume
        if nume_parinte:
            # Căutăm după username sau nume_complet
            row = con.execute("""
                SELECT id, copii FROM utilizatori 
                WHERE LOWER(username) = LOWER(%s) OR LOWER(nume_complet) = LOWER(%s)
                LIMIT 1
            """, (nume_parinte, nume_parinte)).fetchone()

            if row:
                parent_id = row["id"]
                current_copii = _safe_load_list(row["copii"])
            else:
                # B. Dacă nu există, creăm un PĂRINTE PLACEHOLDER (Cont nou automat)
                claim_code = uuid.uuid4().hex[:8].upper()
                cur = con.execute("""
                    INSERT INTO utilizatori (rol, username, is_placeholder, claim_code, created_by_trainer, copii)
                    VALUES ('parinte', %s, 1, %s, 1, '[]')
                    RETURNING id
                """, (nume_parinte, claim_code))
                parent_id = cur.fetchone()["id"]
                current_copii = []
                # (Aici trebuie commit dacă e tranzacție separată, dar facem commit la final)

        else:
            # C. Dacă nu s-a dat nume părinte, nu avem unde să stocăm copilul în structura actuală
            # Putem fie să dăm eroare, fie să-l punem la un părinte generic.
            # Pentru moment, cerem numele părintelui.
            return jsonify(
                {"status": "error", "message": "Te rugăm să introduci numele părintelui pentru a asocia elevul."}), 400

        # Creăm obiectul copil
        new_child = {
            "id": uuid.uuid4().hex,
            "nume": nume_elev,
            "varsta": varsta,
            "gen": gen,
            "grupa": grupa
        }

        # Adăugăm la listă
        current_copii.append(new_child)

        # Actualizăm baza de date (JSON column)
        con.execute("""
            UPDATE utilizatori 
            SET copii = %s 
            WHERE id = %s
        """, (json.dumps(current_copii, ensure_ascii=False), parent_id))

        con.commit()

        return jsonify({
            "status": "success",
            "message": "Elev adăugat cu succes.",
            "elev": new_child
        }), 201

    except Exception as e:
        con.rollback()
        print(f"Eroare add_student: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 3. DELETE: Șterge un elev din JSON-ul părintelui ---
@elevi_bp.delete("/api/elevi/<string:elev_id>")  # ID-ul e string (UUID), nu int
def delete_student(elev_id):
    con = get_conn()
    try:
        # Trebuie să găsim părintele care are acest copil în JSON
        # Această interogare este specifică PostgreSQL pentru a căuta în JSON array
        # Caută rândul unde coloana copii conține un obiect cu id-ul respectiv
        row = con.execute("""
            SELECT id, copii 
            FROM utilizatori 
            WHERE copii::jsonb @> ('[{"id": "' || %s || '"}]')::jsonb
            LIMIT 1
        """, (elev_id,)).fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

        parent_id = row["id"]
        copii_list = _safe_load_list(row["copii"])

        # Filtrăm lista pentru a scoate copilul
        noua_lista = [c for c in copii_list if c.get("id") != elev_id]

        # Salvăm lista actualizată
        con.execute("""
            UPDATE utilizatori 
            SET copii = %s 
            WHERE id = %s
        """, (json.dumps(noua_lista, ensure_ascii=False), parent_id))

        con.commit()
        return jsonify({"status": "success", "message": "Elev șters."})

    except Exception as e:
        con.rollback()
        print(f"Eroare delete_student: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- 4. Endpoint-ul pentru sugestii (pe care l-am reparat anterior) ---
@elevi_bp.get("/api/profil/sugestii_inscriere")
def sugestii_inscriere():
    username = request.args.get('username')
    if not username:
        return jsonify({"status": "error", "message": "Username lipsă"}), 400

    try:
        con = get_conn()
        row_user = con.execute(
            "SELECT id, rol, nume_complet, copii FROM utilizatori WHERE username = %s",
            (username,)
        ).fetchone()

        if not row_user:
            return jsonify({"status": "error", "message": "Utilizator negăsit"}), 404

        user = dict(row_user)
        rol = (user.get('rol') or "").lower()
        nume_propriu = user.get('nume_complet') or username
        lista_copii = []

        if rol in ['parinte', 'admin']:
            copii_raw = user.get('copii')
            if copii_raw:
                date_copii = _safe_load_list(copii_raw)
                for c in date_copii:
                    nume = c.get('nume', '').strip()
                    grupa = c.get('grupa', '')
                    if nume:
                        lista_copii.append({"nume": nume, "grupa": grupa})

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