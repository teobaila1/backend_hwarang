# import re
# from flask import Blueprint, jsonify
# from backend.config import get_conn
#
# reparare_copii_bp = Blueprint('reparare_copii', __name__)
#
#
# def _normalize_name(s):
#     return re.sub(r"\s+", " ", (s or "").strip())
#
#
# def _get_or_create_group_id(cur, group_name):
#     if not group_name: return None
#     gn = _normalize_name(group_name)
#
#     # Normalizare rapidă
#     if gn.isdigit():
#         gn = f"Grupa {gn}"
#     elif gn.lower().startswith("gr") and any(c.isdigit() for c in gn):
#         nums = re.findall(r'\d+', gn)
#         if nums: gn = f"Grupa {nums[0]}"
#
#     cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (gn,))
#     row = cur.fetchone()
#     if row: return row['id']
#     cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (gn,))
#     return cur.fetchone()['id']
#
#
# @reparare_copii_bp.get('/api/admin/repara_linkuri_copii')
# def repara_linkuri():
#     con = get_conn()
#     cur = con.cursor()
#     logs = []
#
#     try:
#         # 1. Selectăm toți copiii care au o grupă scrisă în text, dar poate nu au link
#         cur.execute("SELECT id, nume, grupa_text FROM copii WHERE grupa_text IS NOT NULL AND grupa_text != ''")
#         copii = cur.fetchall()
#
#         count = 0
#         for c in copii:
#             child_id = c['id']
#             nume = c['nume']
#             grupa_text = c['grupa_text']
#
#             # 2. Găsim ID-ul grupei bazat pe text
#             gid = _get_or_create_group_id(cur, grupa_text)
#
#             if gid:
#                 try:
#                     # 3. Încercăm să refacem legătura în sportivi_pe_grupe
#                     # ON CONFLICT DO NOTHING asigură că nu dublăm legăturile existente
#                     cur.execute("""
#                         INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil)
#                         VALUES (%s, %s)
#                         ON CONFLICT DO NOTHING
#                     """, (gid, child_id))
#
#                     logs.append(f"✅ {nume} -> Verificat/Legat la {grupa_text}")
#                     count += 1
#                 except Exception as e:
#                     logs.append(f"❌ Eroare la {nume}: {e}")
#
#         con.commit()
#         return jsonify({
#             "status": "success",
#             "message": f"Am verificat {len(copii)} copii.",
#             "logs": logs
#         })
#
#     except Exception as e:
#         con.rollback()
#         return jsonify({"status": "error", "message": str(e)}), 500
#     finally:
#         con.close()