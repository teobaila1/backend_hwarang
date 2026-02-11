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

    # 1. Date primite
    # Notă: Putem lua username-ul și din token, dar păstrăm logica ta momentan
    username_input = (data.get('username') or '').strip()
    concurs_nume_input = (data.get('concurs') or '').strip()
    nume_sportiv = (data.get("nume") or "").strip()

    # Helper pentru curățare
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

    # Validări de bază
    if not username_input or not concurs_nume_input:
        return jsonify(
            {"status": "error", "message": "Eroare tehnică: Lipsesc datele contului. Încearcă să te reloghezi."}), 400
    if not nume_sportiv:
        return jsonify({"status": "error", "message": "Te rugăm să completezi numele sportivului."}), 400

    con = get_conn()
    try:
        cur = con.cursor()

        # ---------------------------------------------------------
        # PAS 1: Găsim Userul (Case Insensitive)
        # ---------------------------------------------------------
        cur.execute("SELECT email, username FROM utilizatori WHERE LOWER(username) = LOWER(%s)", (username_input,))
        user_row = cur.fetchone()

        if not user_row:
            # Fallback: încercăm după email dacă username-ul nu merge (poate frontend-ul a trimis email)
            cur.execute("SELECT email, username FROM utilizatori WHERE LOWER(email) = LOWER(%s)", (username_input,))
            user_row = cur.fetchone()

        if not user_row:
            return jsonify({"status": "error",
                            "message": "Contul tău nu a fost identificat corect. Te rugăm să te deloghezi și să intri iar."}), 404

        email_real = user_row["email"]
        username_real = user_row["username"]

        # ---------------------------------------------------------
        # PAS 2: Găsim Concursul (CRITIC: Case Insensitive)
        # ---------------------------------------------------------
        # Căutăm concursul ignorând literele mari/mici pentru a evita erorile de tip "Fantomă"
        cur.execute("""
            SELECT nume, inscrieri_deschise 
            FROM concursuri 
            WHERE LOWER(nume) = LOWER(%s)
        """, (concurs_nume_input,))

        concurs_row = cur.fetchone()

        if not concurs_row:
            return jsonify({
                "status": "error",
                "message": f"Concursul '{concurs_nume_input}' nu a fost găsit în baza de date."
            }), 404

        concurs_nume_db = concurs_row['nume']  # Folosim numele corect din DB
        is_open = concurs_row['inscrieri_deschise']

        if is_open is False:
            return jsonify(
                {"status": "error", "message": "Ne pare rău, înscrierile sunt ÎNCHISE pentru acest concurs."}), 403

        # ---------------------------------------------------------
        # PAS 3: Verificare DUPLICAT (Explicație clară)
        # ---------------------------------------------------------
        cur.execute("""
            SELECT id, username FROM inscrieri_concursuri 
            WHERE LOWER(concurs) = LOWER(%s) AND LOWER(nume) = LOWER(%s)
        """, (concurs_nume_db, nume_sportiv))

        existing = cur.fetchone()

        if existing:
            # AICI E CHEIA: Îi spunem cine l-a înscris
            inscris_de = existing['username']
            if inscris_de.lower() == username_real.lower():
                msg = f"{nume_sportiv} este deja înscris de tine."
            else:
                msg = f"{nume_sportiv} a fost deja înscris (probabil de antrenor sau celălalt părinte)."

            return jsonify({
                "status": "error",
                "message": f"Atenție: {msg} Nu este nevoie să îl înscrii din nou."
            }), 409

        # ---------------------------------------------------------
        # PAS 4: INSERARE
        # ---------------------------------------------------------
        cur.execute("""
            INSERT INTO inscrieri_concursuri
                (email, username, concurs, nume, data_nasterii, 
                 categorie_varsta, grad_centura, greutate, inaltime, probe, gen)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (email_real, username_real, concurs_nume_db, nume_sportiv, data_nasterii,
              categorie_varsta, grad_centura, greutate, inaltime, probe, gen))

        con.commit()

        # Trimite mail (fără să blocheze răspunsul)
        def send_async_email():
            try:
                trimite_confirmare_inscriere(email_real, username_real, concurs_nume_db)
            except Exception as e:
                print(f"[MAIL ERROR] {e}")

        Thread(target=send_async_email).start()

        return jsonify({"status": "success", "message": f"Succes! {nume_sportiv} a fost înscris cu succes."}), 201

    except Exception as e:
        if con: con.rollback()
        print(f"[INSCRIERE ERROR] {e}")
        return jsonify({"status": "error", "message": "Eroare internă server: " + str(e)}), 500
    finally:
        if con: con.close()