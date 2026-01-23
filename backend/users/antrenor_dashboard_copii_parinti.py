import json
import re
from datetime import datetime
from flask import request, jsonify, Blueprint
from backend.accounts.decorators import token_required
from backend.config import get_conn

antrenor_dashboard_copii_parinti_bp = Blueprint("antrenor_dashboard_copii_parinti", __name__)


# --- Helper Functions ---
def _calculate_age(dob):
    if not dob: return 0
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d")
        except:
            return 0
    today = datetime.now()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _normalize_group_name(g):
    if not g: return ""
    g = str(g).strip()
    if g.isdigit():
        return f"Grupa {g}"
    if g.lower().startswith("gr") and any(c.isdigit() for c in g):
        nums = re.findall(r'\d+', g)
        if nums:
            return f"Grupa {nums[0]}"
    return g


def _get_or_create_group_id(cur, group_name):
    if not group_name: return None
    g_norm = _normalize_group_name(group_name)
    cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (g_norm,))
    row = cur.fetchone()
    if row: return row['id']
    cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (g_norm,))
    return cur.fetchone()['id']


# --- RUTA 1: Citire Date Dashboard ---
@antrenor_dashboard_copii_parinti_bp.post("/api/antrenor_dashboard_data")
@token_required
def antrenor_dashboard_data():
    data = request.get_json(silent=True) or {}
    trainer_username = (data.get("username") or "").strip()
    if not trainer_username:
        return jsonify({"status": "error", "message": "Lipsă username antrenor."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Identificăm antrenorul
        cur.execute("SELECT id, rol FROM utilizatori WHERE username = %s", (trainer_username,))
        trainer_row = cur.fetchone()
        if not trainer_row:
            return jsonify({"status": "success", "date": []}), 200

        trainer_id = trainer_row['id']

        # 2. Găsim grupele asignate antrenorului
        cur.execute("""
            SELECT DISTINCT g.id, g.nume 
            FROM grupe g
            LEFT JOIN antrenori_pe_grupe ag ON g.id = ag.id_grupa
            WHERE ag.id_antrenor = %s OR g.id_antrenor = %s
            ORDER BY g.nume ASC
        """, (trainer_id, trainer_id))

        grupe_rows = cur.fetchall()
        if not grupe_rows:
            return jsonify({"status": "success", "date": []}), 200

        results = []

        # 3. Procesăm sportivii
        for gr in grupe_rows:
            g_id = gr['id']
            g_nume = gr['nume']

            # A. COPII - Folosim DISTINCT ca să nu apară de 2 ori
            cur.execute("""
                SELECT DISTINCT c.id, c.nume, c.data_nasterii, c.gen,
                       u.id as pid, u.username as puser, u.nume_complet as pfull, u.email as pemail
                FROM sportivi_pe_grupe sg
                JOIN copii c ON sg.id_sportiv_copil = c.id
                LEFT JOIN utilizatori u ON c.id_parinte = u.id
                WHERE sg.id_grupa = %s
            """, (g_id,))
            kids_rows = cur.fetchall()

            # B. ADULȚI - Folosim DISTINCT
            cur.execute("""
                SELECT DISTINCT u.id, u.nume_complet, u.username, u.data_nasterii, u.gen, u.email
                FROM sportivi_pe_grupe sg
                JOIN utilizatori u ON sg.id_sportiv_user = u.id
                WHERE sg.id_grupa = %s
            """, (g_id,))
            adults_rows = cur.fetchall()

            lista_copii = []

            for k in kids_rows:
                # Fallback pt părinte lipsă
                pid = k['pid'] or "unknown"
                p_display = k['pfull'] or k['puser'] or "⚠ Părinte Lipsă/Șters"
                p_email = k['pemail'] or ""

                lista_copii.append({
                    "id": k['id'],
                    "nume": k['nume'],
                    "varsta": _calculate_age(k['data_nasterii']),
                    "gen": k['gen'] or "—",
                    "grupa": g_nume,
                    "tip": "copil",
                    "_parinte_info": {
                        "id": pid,
                        "display": p_display,
                        "email": p_email
                    }
                })

            for a in adults_rows:
                display_name = a['nume_complet'] or a['username']
                lista_copii.append({
                    "id": str(a['id']),
                    "nume": display_name,
                    "varsta": _calculate_age(a['data_nasterii']),
                    "gen": a['gen'] or "—",
                    "grupa": g_nume,
                    "tip": "sportiv",
                    "_parinte_info": {
                        "id": a['id'],
                        "display": f"{display_name} (Sportiv)",
                        "email": a['email']
                    }
                })

            # Grupăm vizual pe familii
            map_familii = {}
            for elev in lista_copii:
                pid = elev["_parinte_info"]["id"]
                if pid == "unknown": pid = f"orph_{elev['id']}"

                if pid not in map_familii:
                    map_familii[pid] = {
                        "parinte": {
                            "id": pid,
                            "display": elev["_parinte_info"]["display"],
                            "email": elev["_parinte_info"]["email"],
                            "username": "..."
                        },
                        "copii": []
                    }
                clean_elev = {k: v for k, v in elev.items() if k != "_parinte_info"}
                map_familii[pid]["copii"].append(clean_elev)

            for pid, val in map_familii.items():
                results.append({
                    "grupa": g_nume,
                    "parinte": val["parinte"],
                    "copii": val["copii"]
                })

        def group_key(item):
            name = item['grupa']
            m = re.search(r"(\d+)", name or "")
            return (int(m.group(1)) if m else 9999, (name or "").lower())

        results.sort(key=lambda x: (group_key(x), x['parinte']['display']))

        return jsonify({"status": "success", "date": results}), 200

    except Exception as e:
        print(f"Eroare SQL Dashboard: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()


# --- RUTA 2: Ștergere Elev ---
@antrenor_dashboard_copii_parinti_bp.delete("/api/elevi/<student_id>")
@token_required
def sterge_elev(student_id):
    con = get_conn()
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM copii WHERE id = %s", (student_id,))
        rows_deleted = cur.rowcount

        if rows_deleted == 0:
            cur.execute("DELETE FROM sportivi_pe_grupe WHERE id_sportiv_user = %s", (student_id,))
            rows_deleted = cur.rowcount

        if rows_deleted > 0:
            con.commit()
            return jsonify({"status": "success", "message": "Elev eliminat."}), 200
        else:
            return jsonify({"status": "error", "message": "Elevul nu a fost găsit."}), 404

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()


# --- RUTA 3: Actualizare Elev ---
@antrenor_dashboard_copii_parinti_bp.patch("/api/elevi/<student_id>")
@token_required
def editeaza_elev(student_id):
    data = request.get_json(silent=True) or {}

    nume = data.get("nume")
    gen = data.get("gen")
    varsta = data.get("varsta")
    grupa_input = data.get("grupa")

    con = get_conn()
    try:
        cur = con.cursor()

        data_nasterii_calc = None
        if varsta and str(varsta).isdigit():
            an_curent = datetime.now().year
            an_nastere = an_curent - int(varsta)
            data_nasterii_calc = f"{an_nastere}-01-01"

        grupa_noua = _normalize_group_name(grupa_input) if grupa_input else None

        fields = []
        vals = []

        if nume:
            fields.append("nume = %s")
            vals.append(nume)
        if gen:
            fields.append("gen = %s")
            vals.append(gen)
        if data_nasterii_calc:
            fields.append("data_nasterii = %s")
            vals.append(data_nasterii_calc)
        if grupa_noua:
            fields.append("grupa_text = %s")
            vals.append(grupa_noua)

        if not fields:
            return jsonify({"status": "success", "message": "Nimic de actualizat."}), 200

        vals.append(student_id)
        sql = f"UPDATE copii SET {', '.join(fields)} WHERE id = %s"

        cur.execute(sql, tuple(vals))

        if cur.rowcount == 0:
            return jsonify({"status": "error",
                            "message": "Nu se pot edita conturile de utilizatori (adulți) din acest meniu."}), 404

        if grupa_noua:
            gid = _get_or_create_group_id(cur, grupa_noua)
            if gid:
                cur.execute("UPDATE sportivi_pe_grupe SET id_grupa = %s WHERE id_sportiv_copil = %s", (gid, student_id))
                if cur.rowcount == 0:
                    cur.execute("INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil) VALUES (%s, %s)",
                                (gid, student_id))

        con.commit()
        return jsonify({"status": "success", "message": "Elev actualizat cu succes."}), 200

    except Exception as e:
        con.rollback()
        print(f"[EDIT ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()