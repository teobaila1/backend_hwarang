from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
from backend.mails.mail_inscriere_concurs_done import trimite_confirmare_inscriere
from threading import Thread  # <--- IMPORT NECESAR (NOU)

inscriere_concurs_bp = Blueprint('inscriere_concurs', __name__)

@inscriere_concurs_bp.post('/api/inscriere_concurs')
@token_required
def inscriere_concurs():
    data = request.get_json(silent=True) or {}

    # 1. Date de identificare (Parent)
    username = (data.get('username') or '').strip()
    concurs_nume = (data.get('concurs') or '').strip()

    # 2. Date Sportiv
    nume_sportiv = (data.get("nume") or "").strip()

    # --- Funcție helper pentru curățare ---
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

    # Probe (poate veni ca listă sau string)
    probe_raw = data.get("probe")
    if isinstance(probe_raw, list):
        probe = ", ".join([str(x).strip() for x in probe_raw if str(x).strip()])
    else:
        probe = str(probe_raw or "").strip()

    # 3. Validări
    if not username or not concurs_nume:
        return jsonify({"status": "error", "message": "Date lipsă: username și concurs sunt obligatorii."}), 400
    if not nume_sportiv:
        return jsonify({"status": "error", "message": "Numele sportivului este obligatoriu."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # 4. Obținem Email-ul părintelui
        cur.execute("SELECT email FROM utilizatori WHERE LOWER(username) = LOWER(%s)", (username,))
        row = cur.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Utilizator inexistent."}), 404
        email = row["email"]

        # 5. Verificăm dacă înscrierile sunt deschise
        cur.execute("SELECT inscrieri_deschise FROM concursuri WHERE nume = %s", (concurs_nume,))
        status_row = cur.fetchone()
        if status_row and status_row['inscrieri_deschise'] is False:
            return jsonify({"status": "error", "message": "Înscrierile sunt ÎNCHISE pentru acest concurs."}), 403

        # 6. Verificăm duplicate (deja înscris?)
        cur.execute("""
            SELECT id FROM inscrieri_concursuri 
            WHERE concurs = %s AND nume = %s
        """, (concurs_nume, nume_sportiv))
        if cur.fetchone():
            return jsonify({"status": "error", "message": f"{nume_sportiv} este deja înscris la {concurs_nume}."}), 409

        # 7. INSERAREA ÎN BAZA DE DATE
        cur.execute("""
            INSERT INTO inscrieri_concursuri
                (email, username, concurs, nume, data_nasterii, 
                 categorie_varsta, grad_centura, greutate, inaltime, probe, gen)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (email, username, concurs_nume, nume_sportiv, data_nasterii,
              categorie_varsta, grad_centura, greutate, inaltime, probe, gen))

        con.commit()

        # --- 8. FIX ASINCRON: Trimitem mailul în fundal ---
        # Asta asigură că utilizatorul primește răspunsul "Succes" INSTANT,
        # chiar dacă mailul durează 10 secunde sau eșuează.
        def send_async_email():
            try:
                trimite_confirmare_inscriere(email, username, concurs_nume)
            except Exception as e:
                print(f"[MAIL BACKGROUND ERROR] {e}")

        Thread(target=send_async_email).start()
        # --------------------------------------------------

        return jsonify({"status": "success", "message": f"Înscriere reușită pentru {concurs_nume}!"}), 201

    except Exception as e:
        con.rollback()
        print(f"[INSCRIERE ERROR] {e}")
        msg = str(e)
        if "invalid input syntax" in msg:
            msg = "Verificați datele introduse (Greutate/Înălțime/Data)."
        return jsonify({"status": "error", "message": msg}), 500
    finally:
        if con: con.close()