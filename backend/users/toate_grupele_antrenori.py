import json
from datetime import datetime
from flask import Blueprint, jsonify
from ..accounts.decorators import token_required, admin_required
from ..config import get_conn

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
    cur = con.cursor()

    # 1. Luăm toți antrenorii care au grupe alocate
    cur.execute("""
        SELECT DISTINCT u.id, u.username, u.nume_complet
        FROM utilizatori u
        JOIN grupe g ON u.id = g.id_antrenor
        WHERE u.rol IN ('Antrenor', 'Admin')
    """)
    trainers = cur.fetchall()

    out = []

    for tr in trainers:
        tid = tr['id']
        tname = tr['username']
        tdisplay = tr['nume_complet'] or tname

        # 2. Luăm grupele acestui antrenor
        cur.execute("SELECT id, nume FROM grupe WHERE id_antrenor = %s ORDER BY nume", (tid,))
        grupe = cur.fetchall()

        grupe_list = []

        for g in grupe:
            gid = g['id']
            gnume = g['nume']

            # 3. Luăm Sportivii din grupă (Copii + Adulți) folosind UNION
            # Această interogare combină cele două tipuri de sportivi într-o singură listă
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

            copii_formatted = []
            for m in members:
                is_sportiv = (m['tip'] == 'sportiv')
                p_display = m['p_full'] or m['p_user']

                copii_formatted.append({
                    "id": m['id'],
                    "nume": m['nume'],
                    "varsta": _calculate_age(m['data_nasterii']),
                    "gen": m['gen'] or "—",
                    "grupa": gnume,
                    "_parent": {
                        "username": m['p_user'],
                        "display": f"{p_display} (Sportiv)" if is_sportiv else p_display,
                        "email": m['p_email']
                    }
                })

            # Sortare alfabetică după nume
            copii_formatted.sort(key=lambda k: (k['nume'] or "").lower())

            grupe_list.append({
                "grupa": gnume,
                "copii": copii_formatted
            })

        out.append({
            "antrenor": tname,
            "antrenor_display": tdisplay,
            "grupe": grupe_list
        })

    # Sortare antrenori
    out.sort(key=lambda r: (r.get("antrenor_display") or "").lower())
    return jsonify({"status": "success", "data": out}), 200