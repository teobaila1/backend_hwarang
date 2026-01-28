import uuid
import re
from flask import Blueprint, request, jsonify
from backend.config import get_conn
from ..accounts.decorators import token_required

elevi_bp = Blueprint("elevi", __name__)


# --- HELPERS ---
def _normalize(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    gn = _normalize(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (gn,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (gn,))
    return cur.fetchone()['id']


# --- 1. GET: Returnează toți elevii (Combinat Copii + Adulți) ---
@elevi_bp.get("/api/elevi")
@token_required
def get_students():
    con = get_conn()
    try:
        cur = con.cursor()
        # Această interogare aduce copiii și face join cu părinții lor
        # Nota: Pentru a vedea și sportivii adulți aici, ar trebui o interogare UNION,
        # dar momentan păstrăm logica pentru copii, așa cum e standard.
        # Dacă Bohdana apare în listă, înseamnă că frontend-ul o ia din alt endpoint sau tabela e deja populată mixt.
        cur.execute("""
            SELECT c.id, c.nume, c.data_nasterii, c.gen, c.grupa_text,
                   u.id as parinte_id, 
                   COALESCE(u.nume_complet, u.username) as parinte_nume
            FROM copii c
            LEFT JOIN utilizatori u ON c.id_parinte = u.id
            ORDER BY c.nume ASC
        """)
        rows = cur.fetchall()

        toti_elevii = []
        for r in rows:
            dn = str(r['data_nasterii']) if r['data_nasterii'] else ""
            toti_elevii.append({
                "id": r['id'],
                "nume": r['nume'],
                "data_nasterii": dn,
                "gen": r['gen'],
                "grupa": r['grupa_text'],
                "parinte_id": r['parinte_id'],
                "parinte_nume": r['parinte_nume']
            })

        # (Opțional) Dacă vrei să vezi și Adulții în lista principală de elevi, ar trebui adăugați aici.
        # Dar ne concentrăm pe EDITARE momentan.

        return jsonify(toti_elevii)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 2. POST: Adaugă un elev (Implicit Copil) ---
@elevi_bp.post("/api/elevi")
@token_required
def add_student():
    data = request.get_json(silent=True) or {}

    nume_elev = _normalize(data.get("nume"))
    data_nasterii = data.get("data_nasterii")
    gen = data.get("gen")
    grupa = _normalize(data.get("grupa"))
    parinte_id = data.get("parinte_id")
    parinte_nume = _normalize(data.get("parent_display") or data.get("parinte_nume"))

    if not nume_elev:
        return jsonify({"status": "error", "message": "Numele elevului este obligatoriu"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        target_parent_id = None

        if parinte_id:
            cur.execute("SELECT id FROM utilizatori WHERE id = %s", (parinte_id,))
            if not cur.fetchone():
                return jsonify({"status": "error", "message": "Părintele selectat nu mai există."}), 404
            target_parent_id = parinte_id
        elif parinte_nume:
            cur.execute("SELECT id FROM utilizatori WHERE LOWER(username) = LOWER(%s)", (parinte_nume,))
            row = cur.fetchone()
            if row:
                target_parent_id = row['id']
            else:
                claim_code = uuid.uuid4().hex[:8].upper()
                dummy_email = f"placeholder_{claim_code}@hwarang.temp"
                cur.execute("""
                    INSERT INTO utilizatori (username, email, parola, rol, is_placeholder, claim_code, copii, grupe)
                    VALUES (%s, %s, 'NO_LOGIN', 'Parinte', 1, %s, '[]', '')
                    RETURNING id
                """, (parinte_nume, dummy_email, claim_code))
                target_parent_id = cur.fetchone()['id']
                cur.execute("INSERT INTO roluri (id_user, rol) VALUES (%s, 'Parinte')", (target_parent_id,))
        else:
            return jsonify({"status": "error", "message": "Trebuie să selectezi un părinte."}), 400

        new_id = uuid.uuid4().hex
        cur.execute("""
            INSERT INTO copii (id, id_parinte, nume, data_nasterii, gen, grupa_text, added_by_trainer)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        """, (new_id, target_parent_id, nume_elev, data_nasterii, gen, grupa))

        if grupa:
            gid = _get_or_create_group_id(cur, grupa)
            if gid:
                cur.execute("""
                    INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) 
                    VALUES (%s, %s)
                    ON CONFLICT (id_grupa, id_sportiv_copil) DO NOTHING
                """, (gid, new_id))

        con.commit()
        return jsonify({"status": "success", "message": "Elev adăugat cu succes."}), 201
    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 3. PATCH: Modifică un elev (REPARAT PENTRU ID 25) ---
@elevi_bp.patch("/api/elevi/<string:elev_id>")
@token_required
def update_student(elev_id):
    data = request.get_json(silent=True) or {}

    nume = _normalize(data.get("nume"))
    data_nasterii = data.get("data_nasterii")
    gen = data.get("gen")
    grupa = _normalize(data.get("grupa"))

    # Nume părinte (relevant doar la copii)
    parinte_nume_nou = _normalize(data.get("parinte_nume") or data.get("parent_display"))
    parinte_id = data.get("parinte_id")

    con = get_conn()
    try:
        cur = con.cursor()
        updated_child = False
        updated_sportiv = False

        # --- LOGICA NOUĂ: Verificăm TIPUL ID-ului ---
        # ID-ul 25 este numeric. ID-ul de copil este UUID (string cu litere si cifre).
        is_user_id = str(elev_id).isdigit()

        if not is_user_id:
            # === CAZ 1: Este COPIL (UUID) ===
            # Facem update doar în tabela copii
            fields = []
            values = []
            if nume: fields.append("nume = %s"); values.append(nume)
            if data_nasterii: fields.append("data_nasterii = %s"); values.append(data_nasterii)
            if gen: fields.append("gen = %s"); values.append(gen)
            if grupa is not None: fields.append("grupa_text = %s"); values.append(grupa)

            if fields:
                vals_copil = list(values)
                vals_copil.append(elev_id)
                cur.execute(f"UPDATE copii SET {', '.join(fields)} WHERE id = %s", tuple(vals_copil))
                if cur.rowcount > 0:
                    updated_child = True

        else:
            # === CAZ 2: Este SPORTIV ADULT (User ID numeric - ex: 25) ===
            # Facem update doar în tabela utilizatori
            fields_u = []
            values_u = []
            if nume: fields_u.append("nume_complet = %s"); values_u.append(nume)
            if data_nasterii: fields_u.append("data_nasterii = %s"); values_u.append(data_nasterii)
            if gen: fields_u.append("gen = %s"); values_u.append(gen)

            if fields_u:
                values_u.append(elev_id)
                # Acum sigur e numeric, nu mai crapă
                cur.execute(f"UPDATE utilizatori SET {', '.join(fields_u)} WHERE id = %s", tuple(values_u))
                if cur.rowcount > 0:
                    updated_sportiv = True

        if not updated_child and not updated_sportiv:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

        # --- C. Actualizare Grupă (Tabela sportivi_pe_grupe) ---
        if grupa:
            gid = _get_or_create_group_id(cur, grupa)

            if updated_child:
                # Actualizăm legătura pentru COPIL
                cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_copil = %s", (elev_id,))
                if gid:
                    cur.execute("""
                        INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) 
                        VALUES (%s, %s)
                        ON CONFLICT (id_grupa, id_sportiv_copil) DO NOTHING
                    """, (gid, elev_id))

            elif updated_sportiv:
                # Actualizăm legătura pentru SPORTIV (Folosim id_sportiv_user!)
                # Ștergem orice legătură veche a acestui user
                cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (elev_id,))
                if gid:
                    cur.execute("""
                        INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_user) 
                        VALUES (%s, %s)
                        ON CONFLICT (id_grupa, id_sportiv_user) DO NOTHING
                    """, (gid, elev_id))

        # --- D. Update Nume Părinte (Doar dacă e Copil și părintele e placeholder) ---
        if updated_child and parinte_nume_nou and parinte_id:
            cur.execute("SELECT is_placeholder FROM utilizatori WHERE id = %s", (parinte_id,))
            row = cur.fetchone()
            if row and row['is_placeholder'] == 1:
                cur.execute("UPDATE utilizatori SET username = %s, nume_complet = %s WHERE id = %s",
                            (parinte_nume_nou, parinte_nume_nou, parinte_id))

        con.commit()
        return jsonify({"status": "success", "message": "Date actualizate."}), 200

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 4. DELETE: Șterge un elev ---
@elevi_bp.delete("/api/elevi/<string:elev_id>")
@token_required
def delete_student(elev_id):
    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Încercăm ștergere din COPII
        cur.execute("DELETE FROM copii WHERE id = %s", (elev_id,))
        if cur.rowcount > 0:
            con.commit()
            return jsonify({"status": "success", "message": "Elev (copil) șters."})

        # 2. Dacă nu, poate e SPORTIV? (Nu ștergem contul, doar îl scoatem din grupă)
        # Verificăm dacă e un ID de user (întreg)
        if str(elev_id).isdigit():
            cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (elev_id,))
            con.commit()
            return jsonify({"status": "success", "message": "Sportiv eliminat din grupă."})

        return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 5. SUGESTII PENTRU ÎNSCRIERE CONCURS ---
@elevi_bp.get("/api/profil/sugestii_inscriere")
@token_required
def sugestii_inscriere():
    username = request.args.get('username')
    if not username: return jsonify({"status": "error", "message": "Username lipsă"}), 400

    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("SELECT id, rol, nume_complet FROM utilizatori WHERE username=%s", (username,))
        row = cur.fetchone()
        if not row: return jsonify({"status": "error", "message": "User not found"}), 404
        user_id = row['id']
        rol = (row['rol'] or "").lower()
        nume_propriu = row['nume_complet'] or username
        copii_list = []
        if rol in ['parinte', 'admin']:
            cur.execute("SELECT nume, grupa_text, data_nasterii, gen FROM copii WHERE id_parinte = %s", (user_id,))
            rows_copii = cur.fetchall()
            for c in rows_copii:
                copii_list.append({
                    "nume": c['nume'],
                    "grupa": c['grupa_text'],
                    "data_nasterii": str(c['data_nasterii']) if c['data_nasterii'] else "",
                    "gen": c['gen']
                })
        return jsonify({"status": "success", "data": {"rol": rol, "nume_propriu": nume_propriu, "copii": copii_list}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()