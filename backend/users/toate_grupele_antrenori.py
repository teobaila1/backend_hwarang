from datetime import datetime
from flask import Blueprint, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required, admin_required

toate_grupele_antrenori_bp = Blueprint('toate_grupele_antrenori', __name__)


def _calculate_age(dob):
    if not dob: return 0
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d")
        except:
            return 0
    today = datetime.now()
    # Verificăm dacă dob e obiect date sau datetime
    try:
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except:
        return 0


@toate_grupele_antrenori_bp.get("/api/toate_grupele_antrenori")
@token_required
@admin_required
def get_all_groups_and_athletes():
    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Luăm toți antrenorii și adminii
        cur.execute("SELECT id, username, nume_complet FROM utilizatori WHERE LOWER(rol) IN ('antrenor', 'admin')")
        potential_trainers = cur.fetchall()

        out = []

        for tr in potential_trainers:
            tid = tr['id']
            tname = tr['username']
            tdisplay = tr['nume_complet'] or tname

            grupe_list = []

            # 2. Căutăm grupele asociate acestui antrenor
            try:
                cur.execute("""
                    SELECT g.id, g.nume 
                    FROM grupe g
                    JOIN antrenori_pe_grupe ag ON g.id = ag.id_grupa
                    WHERE ag.id_antrenor = %s
                    ORDER BY g.nume
                """, (tid,))
                grupe = cur.fetchall()
            except:
                con.rollback()
                cur = con.cursor()
                grupe = []

            for g in grupe:
                gid = g['id']
                gnume = g['nume']
                lista_membri = []

                # --- A. Luăm COPIII din grupă ---
                try:
                    cur.execute("""
                        SELECT c.id, c.nume, c.data_nasterii, c.gen, c.id_parinte,
                               u.username as p_user, u.nume_complet as p_full
                        FROM sportivi_pe_grupe sg
                        JOIN copii c ON sg.id_sportiv_copil = c.id
                        LEFT JOIN utilizatori u ON c.id_parinte = u.id
                        WHERE sg.id_grupa = %s
                    """, (gid,))
                    copii_rows = cur.fetchall()
                except:
                    con.rollback()
                    cur = con.cursor()
                    copii_rows = []

                for c in copii_rows:
                    dn_str = str(c['data_nasterii']) if c['data_nasterii'] else ""
                    gen_cap = (c['gen'] or "").capitalize() if c['gen'] else "—"
                    p_display = c.get('p_full') or c.get('p_user') or "—"

                    lista_membri.append({
                        "id": c['id'],
                        "nume": c['nume'],
                        "varsta": _calculate_age(c['data_nasterii']),
                        "data_nasterii": dn_str,
                        "gen": gen_cap,
                        "grupa": gnume,
                        "tip": "copil",
                        "_parent": {
                            "id": c['id_parinte'],
                            "username": c.get('p_user'),
                            "display": p_display
                        }
                    })

                # --- B. Luăm SPORTIVII ADULȚI (Useri) din grupă ---
                try:
                    cur.execute("""
                        SELECT u.id, u.nume_complet, u.username, u.data_nasterii, u.gen
                        FROM sportivi_pe_grupe sg
                        JOIN utilizatori u ON sg.id_sportiv_user = u.id
                        WHERE sg.id_grupa = %s
                    """, (gid,))
                    adulti_rows = cur.fetchall()
                except:
                    con.rollback()
                    cur = con.cursor()
                    adulti_rows = []

                for u in adulti_rows:
                    dn_str = str(u['data_nasterii']) if u['data_nasterii'] else ""
                    gen_cap = (u['gen'] or "").capitalize() if u['gen'] else "—"
                    nume_afisat = u['nume_complet'] or u['username']

                    lista_membri.append({
                        "id": u['id'],  # ID numeric (ex: 25)
                        "nume": nume_afisat,
                        "varsta": _calculate_age(u['data_nasterii']),
                        "data_nasterii": dn_str,
                        "gen": gen_cap,
                        "grupa": gnume,
                        "tip": "adult",
                        # La adulți nu avem părinte, punem o etichetă specială
                        "_parent": {
                            "id": None,
                            "display": "Sportiv Independent"
                        }
                    })

                # Sortăm alfabetic toată lista din grupă
                lista_membri.sort(key=lambda x: (x['nume'] or "").lower())

                grupe_list.append({
                    "id_grupa": gid,
                    "grupa": gnume,
                    "copii": lista_membri
                })

            if grupe_list:
                out.append({
                    "antrenor": tname,
                    "antrenor_display": tdisplay,
                    "grupe": grupe_list
                })

        out.sort(key=lambda r: (r.get("antrenor_display") or "").lower())
        return jsonify({"status": "success", "data": out}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()