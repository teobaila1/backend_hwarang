import json
from datetime import datetime
from flask import Blueprint, jsonify
from backend.accounts.decorators import token_required, admin_required
from backend.config import get_conn

toate_grupele_antrenori_bp = Blueprint('toate_grupele_antrenori', __name__)


def _calculate_age(dob):
    if not dob: return 0
    if isinstance(dob, str):
        try:
            dob = datetime.strptime(dob, "%Y-%m-%d")
        except:
            return 0
    today = datetime.now()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


@toate_grupele_antrenori_bp.get("/api/toate_grupele_antrenori")
@token_required
@admin_required
def toate_grupele_antrenori():
    con = get_conn()
    try:
        cur = con.cursor()

        # 1. Luăm toți antrenorii
        cur.execute("SELECT * FROM utilizatori WHERE LOWER(rol) IN ('antrenor', 'admin')")
        potential_trainers = cur.fetchall()

        out = []

        for tr in potential_trainers:
            tid = tr['id']
            tname = tr['username']
            tdisplay = tr.get('nume_complet') or tname

            grupe_list = []
            try:
                # 2. Căutăm grupele în tabelul nou
                cur.execute("""
                    SELECT g.id, g.nume 
                    FROM grupe g
                    JOIN antrenori_pe_grupe ag ON g.id = ag.id_grupa
                    WHERE ag.id_antrenor = %s
                    ORDER BY g.nume
                """, (tid,))
                grupe = cur.fetchall()

                # Fallback pe metoda veche dacă tabelul e gol pentru acest user
                if not grupe:
                    cur.execute("SELECT id, nume FROM grupe WHERE id_antrenor = %s", (tid,))
                    grupe = cur.fetchall()
            except:
                con.rollback()
                cur = con.cursor()
                grupe = []

            for g in grupe:
                gid = g['id']
                gnume = g['nume']

                # 3. Luăm sportivii
                try:
                    cur.execute("""
                        SELECT c.id, c.nume, c.data_nasterii, c.gen, 'copil' as tip,
                               u.username as p_user, u.nume_complet as p_full, u.email as p_email
                        FROM sportivi_pe_grupe sg
                        JOIN copii c ON sg.id_sportiv_copil = c.id
                        JOIN utilizatori u ON c.id_parinte = u.id
                        WHERE sg.id_grupa = %s
                        UNION ALL
                        SELECT CAST(u.id AS TEXT), COALESCE(u.nume_complet, u.username), u.data_nasterii, u.gen, 'sportiv' as tip,
                               u.username, u.nume_complet, u.email
                        FROM sportivi_pe_grupe sg
                        JOIN utilizatori u ON sg.id_sportiv_user = u.id
                        WHERE sg.id_grupa = %s
                    """, (gid, gid))
                    members = cur.fetchall()
                except:
                    con.rollback()
                    cur = con.cursor()
                    members = []

                copii_formatted = []
                for m in members:
                    is_sportiv = (m['tip'] == 'sportiv')
                    p_display = m.get('p_full') or m.get('p_user') or "Unknown"
                    copii_formatted.append({
                        "id": m['id'],
                        "nume": m['nume'],
                        "varsta": _calculate_age(m['data_nasterii']),
                        "gen": m['gen'] or "—",
                        "grupa": gnume,
                        "_parent": {
                            "username": m.get('p_user'),
                            "display": f"{p_display} (Sportiv)" if is_sportiv else p_display,
                            "email": m.get('p_email')
                        }
                    })

                copii_formatted.sort(key=lambda k: (k['nume'] or "").lower())
                grupe_list.append({"grupa": gnume, "copii": copii_formatted})

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