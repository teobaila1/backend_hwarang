from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
from backend.mails.mail_inscriere_concurs_done import trimite_confirmare_inscriere
from threading import Thread

inscriere_concurs_bp = Blueprint('inscriere_concurs', __name__)


@inscriere_concurs_bp.post('/api/inscriere_concurs')
@token_required
def inscriere_concurs():
    data = request.get_json(silent=True) or {}

    # 1. Date de identificare (Parent)
    username_input = (data.get('username') or '').strip()
    concurs_nume = (data.get('concurs') or '').strip()

    # 2. Date Sportiv
    nume_sportiv = (data.get("nume") or "").strip()

    def clean_input(val):
        if not val: return None
        s = str(val).strip()
        return s if s else None

    data_nasterii = clean_input(data.get("dataNasterii"))
    categorie_varsta = clean_input(data.get("categorieVarsta") or data.get("categorie"))
    grad_centura = clean_input(data.get("gradCentura") or data.get("grad"))
    greutate = clean_input(data.get("greutate"))
    inaltime = clean_input(data.get("inaltime"))
    gen = clean_input(data.get("gen"))

    probe_raw = data.get("probe")
    if isinstance(probe_raw, list):
        probe = ", ".join([str(x).strip() for x in probe_raw if str(x).strip()])
    else:
        probe = str(probe_raw or "").strip()

    # 3. Validări primare
    if not username_input or not concurs_nume:
        return jsonify({"status": "error", "message": "Date lipsă: username și concurs sunt obligatorii."}), 400
    if not nume_sportiv:
        return jsonify({"status": "error", "message": "Numele sportivului este obligatoriu."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 4. Obținem Email-ul și USERNAME-UL REAL (din DB)
        # (Rezolvă problema cu litere mari/mici de la telefon)
        cur.execute("SELECT email, username FROM utilizatori WHERE LOWER(username) = LOWER(%s)", (username_input,))
        row = cur.fetchone()

        if not row:
            return jsonify({"status": "error", "message": "Utilizator inexistent."}), 404

        email = row["email"]
        real_username = row["username"]

        # 5. Verificăm existența concursului (Fix critic pentru concursuri fantomă)
        cur.execute("SELECT inscrieri_deschise FROM concursuri WHERE nume = %s", (concurs_nume,))
        status_row = cur.fetchone()

        if not status_row:
            return jsonify({"status": "error",
                            "message": f"Eroare: Concursul '{concurs_nume}' nu a fost găsit. Contactați administratorul."}), 404

        if status_row['inscrieri_deschise'] is False:
            return jsonify({"status": "error", "message": "Înscrierile sunt ÎNCHISE pentru acest concurs."}), 403

        # --- 6. FIXUL SOLICITAT: MESAJ CLAR PENTRU DUPLICATE ---
        # Verificăm dacă sportivul e deja înscris (ignoring case)
        cur.execute("""
            SELECT id FROM inscrieri_concursuri 
            WHERE concurs = %s AND LOWER(nume) = LOWER(%s)
        """, (concurs_nume, nume_sportiv))

        if cur.fetchone():
            # AICI trimitem mesajul roșu pe care îl doreai
            return jsonify({
                "status": "error",
                "message": f"Atenție: {nume_sportiv} este deja înscris la acest concurs!"
            }), 409
        # -------------------------------------------------------

        # 7. INSERAREA ÎN BAZA DE DATE
        cur.execute("""
            INSERT INTO inscrieri_concursuri
                (email, username, concurs, nume, data_nasterii, 
                 categorie_varsta, grad_centura, greutate, inaltime, probe, gen)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (email, real_username, concurs_nume, nume_sportiv, data_nasterii,
              categorie_varsta, grad_centura, greutate, inaltime, probe, gen))

        con.commit()

        # 8. Trimitere mail asincron
        def send_async_email():
            try:
                trimite_confirmare_inscriere(email, real_username, concurs_nume)
            except Exception as e:
                print(f"[MAIL ERROR] {e}")

        Thread(target=send_async_email).start()

        return jsonify({"status": "success", "message": f"Înscriere reușită pentru {concurs_nume}!"}), 201

    except Exception as e:
        con.rollback()
        print(f"[INSCRIERE ERROR] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if con: con.close()