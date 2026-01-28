import uuid
import re
import json
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


# --- 1. GET: Returnează toți elevii ---
@elevi_bp.get("/api/elevi")
@token_required
def get_students():
    con = get_conn()
    try:
        cur = con.cursor()
        # Aici aducem copiii. (Dacă ai nevoie și de Sportivii Adulți în această listă, ar trebui făcut un UNION,
        # dar momentan funcția e gândită pentru a popula tabelele de copii).
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

        return jsonify(toti_elevii)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 2. POST: Adaugă un elev ---
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


# --- 3. PATCH: Modifică un elev (SOLUȚIA ROBUSTĂ CU ROLLBACK) ---
@elevi_bp.patch("/api/elevi/<string:elev_id>")
@token_required
def update_student(elev_id):
    data = request.get_json(silent=True) or {}

    nume = _normalize(data.get("nume"))
    data_nasterii = data.get("data_nasterii")
    gen = data.get("gen")
    grupa = _normalize(data.get("grupa"))

    parinte_nume_nou = _normalize(data.get("parinte_nume") or data.get("parent_display"))
    parinte_id = data.get("parinte_id")

    con = get_conn()
    try:
        cur = con.cursor()
        updated_child = False
        updated_sportiv = False

        # Verificăm formatul doar ca optimizare, dar ne bazăm pe DB pentru siguranță
        is_probably_user = str(elev_id).isdigit()

        # --- ÎNCERCARE 1: Dacă pare ID numeric, încercăm PRIMA DATĂ la Useri ---
        if is_probably_user:
            fields_u = []
            values_u = []
            if nume: fields_u.append("nume_complet = %s"); values_u.append(nume)
            if data_nasterii: fields_u.append("data_nasterii = %s"); values_u.append(data_nasterii)
            if gen: fields_u.append("gen = %s"); values_u.append(gen)

            if fields_u:
                values_u.append(elev_id)
                try:
                    cur.execute(f"UPDATE utilizatori SET {', '.join(fields_u)} WHERE id = %s", tuple(values_u))
                    if cur.rowcount > 0:
                        updated_sportiv = True
                except Exception as e:
                    # CHEIA SUCCESULUI: Resetăm tranzacția dacă crapă ceva aici!
                    print(f"Eroare update user (dar continuam): {e}")
                    con.rollback()
                    # Re-deschidem cursorul după rollback
                    cur = con.cursor()

        # --- ÎNCERCARE 2: Dacă nu am actualizat user (sau nu părea user), încercăm la Copii ---
        if not updated_sportiv:
            fields = []
            values = []
            if nume: fields.append("nume = %s"); values.append(nume)
            if data_nasterii: fields.append("data_nasterii = %s"); values.append(data_nasterii)
            if gen: fields.append("gen = %s"); values.append(gen)
            if grupa is not None: fields.append("grupa_text = %s"); values.append(grupa)

            if fields:
                vals_copil = list(values)
                vals_copil.append(elev_id)
                try:
                    cur.execute(f"UPDATE copii SET {', '.join(fields)} WHERE id = %s", tuple(vals_copil))
                    if cur.rowcount > 0:
                        updated_child = True
                except Exception as e:
                    # Resetăm tranzacția dacă ID-ul "25" ajunge la copii și dă eroare UUID
                    print(f"Eroare update copil (posibil id de adult): {e}")
                    con.rollback()
                    cur = con.cursor()

        # --- ÎNCERCARE 3: Dacă tot nu am găsit nimic, și am sărit pasul 1 (pt că nu era digit), încercăm Useri acum ---
        # (Acesta e un caz rar: useri cu ID-uri non-numerice pe viitor)
        if not updated_child and not updated_sportiv and not is_probably_user:
            # Repetăm logica de user (opțional, dar bun pentru siguranță completă)
            pass

        if not updated_child and not updated_sportiv:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit (nici copil, nici sportiv)."}), 404

        # --- C. Actualizare Grupă ---
        if grupa:
            gid = _get_or_create_group_id(cur, grupa)

            if updated_child:
                cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_copil = %s", (elev_id,))
                if gid:
                    cur.execute("""
                        INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) 
                        VALUES (%s, %s)
                        ON CONFLICT (id_grupa, id_sportiv_copil) DO NOTHING
                    """, (gid, elev_id))

            elif updated_sportiv:
                cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (elev_id,))
                if gid:
                    cur.execute("""
                        INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_user) 
                        VALUES (%s, %s)
                        ON CONFLICT (id_grupa, id_sportiv_user) DO NOTHING
                    """, (gid, elev_id))

        # --- D. Update Nume Părinte (Doar la copii) ---
        if updated_child and parinte_nume_nou and parinte_id:
            try:
                cur.execute("SELECT is_placeholder FROM utilizatori WHERE id = %s", (parinte_id,))
                row = cur.fetchone()
                if row and row['is_placeholder'] == 1:
                    cur.execute("UPDATE utilizatori SET username = %s, nume_complet = %s WHERE id = %s",
                                (parinte_nume_nou, parinte_nume_nou, parinte_id))
            except:
                con.rollback()

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

        # Logica robustă: Încercăm ambele cu Rollback între ele
        deleted = False

        # 1. Copil
        try:
            cur.execute("DELETE FROM copii WHERE id = %s", (elev_id,))
            if cur.rowcount > 0: deleted = True
        except:
            con.rollback()
            cur = con.cursor()

        # 2. Sportiv (User)
        if not deleted:
            try:
                # Verificare simplă de siguranță pt ID numeric
                if str(elev_id).isdigit():
                    cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (elev_id,))
                    # Nu ștergem userul, doar din grupă. Putem considera "deleted" pt UI.
                    deleted = True
            except:
                con.rollback()

        if deleted:
            con.commit()
            return jsonify({"status": "success", "message": "Elev șters/scos din grupă."})
        else:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


# --- 5. SUGESTII ---
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