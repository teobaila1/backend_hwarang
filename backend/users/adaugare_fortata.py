# import uuid
# import re
# from flask import Blueprint, request, jsonify
# from backend.config import get_conn
# from backend.accounts.decorators import token_required, admin_required
#
# adaugare_fortata_bp = Blueprint('adaugare_fortata', __name__)
#
#
# def _normalize_group_name(g):
#     if not g: return ""
#     g = str(g).strip()
#     if g.isdigit():
#         return f"Grupa {g}"
#     if g.lower().startswith("gr") and any(c.isdigit() for c in g):
#         nums = re.findall(r'\d+', g)
#         if nums: return f"Grupa {nums[0]}"
#     return g
#
#
# def _get_or_create_group_id(cur, group_name):
#     gn = _normalize_group_name(group_name)
#     cur.execute("SELECT id FROM grupe WHERE LOWER(nume) = LOWER(%s)", (gn,))
#     row = cur.fetchone()
#     if row: return row['id']
#     cur.execute("INSERT INTO grupe (nume) VALUES (%s) RETURNING id", (gn,))
#     return cur.fetchone()['id']
#
#
# @adaugare_fortata_bp.post('/api/admin/adauga_copil_manual')
# @token_required
# @admin_required
# def adauga_copil_manual():
#     # Așteptăm JSON: { "email_parinte": "...", "nume_copil": "...", "grupa": "..." }
#     data = request.get_json(silent=True) or {}
#
#     email_parinte = (data.get("email_parinte") or "").strip()
#     nume_copil = (data.get("nume_copil") or "").strip()
#     grupa_input = (data.get("grupa") or "").strip()
#
#     if not email_parinte or not nume_copil or not grupa_input:
#         return jsonify({"status": "error", "message": "Completează: email_parinte, nume_copil, grupa"}), 400
#
#     con = get_conn()
#     try:
#         cur = con.cursor()
#
#         # 1. Găsim Părintele după Email (Asta e cheia!)
#         cur.execute("SELECT id, nume_complet FROM utilizatori WHERE LOWER(email) = LOWER(%s)", (email_parinte,))
#         parent_row = cur.fetchone()
#
#         if not parent_row:
#             return jsonify({"status": "error", "message": f"Nu există niciun părinte cu emailul {email_parinte}"}), 404
#
#         parent_id = parent_row['id']
#         parent_name = parent_row['nume_complet']
#
#         # 2. Găsim/Creăm Grupa
#         gid = _get_or_create_group_id(cur, grupa_input)
#         nume_grupa_final = _normalize_group_name(grupa_input)
#
#         # 3. Verificăm dacă copilul există deja (poate l-ai șters doar din grupă, nu și din tabelul copii)
#         cur.execute("SELECT id FROM copii WHERE id_parinte = %s AND LOWER(nume) = LOWER(%s)", (parent_id, nume_copil))
#         child_row = cur.fetchone()
#
#         if child_row:
#             child_id = child_row['id']
#             msg_action = "Copilul exista deja, am refăcut legătura."
#             # Actualizăm textul grupei
#             cur.execute("UPDATE copii SET grupa_text = %s WHERE id = %s", (nume_grupa_final, child_id))
#         else:
#             # 4. Dacă nu există, îl CREĂM
#             child_id = uuid.uuid4().hex
#             # Punem data nașterii NULL momentan (o poți edita din dashboard după aia)
#             cur.execute("""
#                 INSERT INTO copii (id, id_parinte, nume, grupa_text, added_by_trainer)
#                 VALUES (%s, %s, %s, %s, TRUE)
#             """, (child_id, parent_id, nume_copil, nume_grupa_final))
#             msg_action = "Am creat copilul de la zero."
#
#         # 5. Facem Legătura în sportivi_pe_grupe
#         cur.execute("""
#             INSERT INTO sportivi_pe_grupe (id_grupa, id_sportiv_copil)
#             VALUES (%s, %s)
#             ON CONFLICT (id_grupa, id_sportiv_copil) DO NOTHING
#         """, (gid, child_id))
#
#         con.commit()
#         return jsonify({
#             "status": "success",
#             "message": f"{msg_action} {nume_copil} a fost adăugat la {nume_grupa_final} (Părinte: {parent_name})."
#         }), 200
#
#     except Exception as e:
#         con.rollback()
#         return jsonify({"status": "error", "message": str(e)}), 500
#     finally:
#         con.close()