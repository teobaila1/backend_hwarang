from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
from backend.mails.mail_inscriere_concurs_done import trimite_confirmare_inscriere
from threading import Thread

inscriere_concurs_bp = Blueprint('inscriere_concurs', __name__)


@inscriere_concurs_bp.post('/api/inscriere_concurs')
@token_required
def inscriere_concurs():
    # AICI E CHEIA: Luăm ID-ul direct din token, nu așteptăm username de la frontend
    user_id_curent = request.user_id

    data = request.get_json(silent=True) or {}

    # 1. Preluăm numele concursului și al sportivului
    concurs_nume_input = (data.get('concurs') or '').strip()
    nume_sportiv = (data.get("nume") or "").strip()

    # Helper curățare
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

    # Validări minime (NU mai verificăm username_input aici!)
    if not concurs_nume_input:
        return jsonify({"status": "error", "message": "Lipsește numele concursului."}), 400
    if not nume_sportiv:
        return jsonify({"status": "error", "message": "Te rugăm să completezi numele sportivului."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # ------------------------------------------------------------------
        # PAS 1: IDENTIFICARE SIGURĂ (După ID din Token)
        # ------------------------------------------------------------------
        cur.execute("SELECT email, username FROM utilizatori WHERE id = %s", (user_id_curent,))
        user_row = cur.fetchone()

        if not user_row:
            return jsonify({"status": "error", "message": "Sesiune expirată. Te rugăm să te re-autentifici."}), 401

        email_real = user_row["email"]
        username_real = user_row["username"]

        # ------------------------------------------------------------------
        # PAS 2: Găsim Concursul (Case Insensitive)
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT nume, inscrieri_deschise 
            FROM concursuri 
            WHERE LOWER(nume) = LOWER(%s)
        """, (concurs_nume_input,))

        concurs_row = cur.fetchone()

        if not concurs_row:
            return jsonify({"status": "error", "message": f"Concursul '{concurs_nume_input}' nu a fost găsit."}), 404

        concurs_nume_db = concurs_row['nume']

        if concurs_row['inscrieri_deschise'] is False:
            return jsonify({"status": "error", "message": "Înscrierile sunt închise pentru acest concurs."}), 403

        # ------------------------------------------------------------------
        # PAS 3: Verificare DUPLICAT
        # ------------------------------------------------------------------
        cur.execute("""
            SELECT username FROM inscrieri_concursuri 
            WHERE LOWER(concurs) = LOWER(%s) AND LOWER(nume) = LOWER(%s)
        """, (concurs_nume_db, nume_sportiv))

        existing = cur.fetchone()

        if existing:
            inscris_de = existing['username']
            if inscris_de.lower() != username_real.lower():
                return jsonify({
                    "status": "error",
                    "message": f"Acest copil este deja înscris de '{inscris_de}'. Nu trebuie să mai faci nimic."
                }), 409
            else:
                return jsonify({
                    "status": "error",
                    "message": "Ai trimis deja înscrierea pentru acest sportiv."
                }), 409

        # ------------------------------------------------------------------
        # PAS 4: INSERT
        # ------------------------------------------------------------------
        cur.execute("""
            INSERT INTO inscrieri_concursuri
                (email, username, concurs, nume, data_nasterii, 
                 categorie_varsta, grad_centura, greutate, inaltime, probe, gen)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (email_real, username_real, concurs_nume_db, nume_sportiv, data_nasterii,
              categorie_varsta, grad_centura, greutate, inaltime, probe, gen))

        con.commit()

        def send_async_email():
            try:
                trimite_confirmare_inscriere(email_real, username_real, concurs_nume_db)
            except Exception:
                pass

        Thread(target=send_async_email).start()

        return jsonify({"status": "success", "message": "Înscriere reușită!"}), 201

    except Exception as e:
        if con: con.rollback()
        print(f"[EROARE INSCRIERE]: {e}")
        return jsonify({"status": "error", "message": "Eroare server. Încearcă din nou."}), 500
    finally:
        if con: con.close()