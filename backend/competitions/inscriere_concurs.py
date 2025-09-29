from flask import Blueprint, request, jsonify
from ..config import get_conn, DB_PATH  # o singură sursă pentru DB

inscriere_concurs_bp = Blueprint('inscriere_concurs', __name__)

@inscriere_concurs_bp.post('/api/inscriere_concurs')
def inscriere_concurs():
    data = request.get_json(silent=True) or {}

    username = (data.get('username') or '').strip()
    concurs  = (data.get('concurs')  or '').strip()

    # câmpuri din formular
    nume            = (data.get("nume")            or "").strip()
    data_nasterii   = (data.get("dataNasterii")    or "").strip()
    categorie_varsta= (data.get("categorieVarsta") or "").strip()
    grad_centura    = (data.get("gradCentura")     or "").strip()
    greutate        = (data.get("greutate")        or "").strip()
    probe           = data.get("probe")  # poate fi listă sau string
    gen             = (data.get("gen")            or "").strip()

    # validări minime
    if not username or not concurs:
        return jsonify({"status": "error", "message": "Date lipsă: username și concurs sunt obligatorii."}), 400
    if not nume:
        return jsonify({"status": "error", "message": "Câmpul 'nume' este obligatoriu."}), 400

    # normalizăm 'probe' (acceptăm listă sau string)
    if isinstance(probe, list):
        probe = ", ".join([str(x).strip() for x in probe if str(x).strip()])
    elif probe is None:
        probe = ""

    try:
        con = get_conn()

        # emailul se obține din tabela utilizatori
        row = con.execute("SELECT email FROM utilizatori WHERE username = ?", (username,)).fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Utilizator inexistent."}), 404
        email = row["email"]

        # Asigurăm tabela (include și 'gen')
        con.execute("""
            CREATE TABLE IF NOT EXISTS inscrieri_concursuri (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                email           TEXT,
                username        TEXT,
                concurs         TEXT,
                nume            TEXT,
                data_nasterii   TEXT,
                categorie_varsta TEXT,
                grad_centura    TEXT,
                greutate        TEXT,
                probe           TEXT,
                gen             TEXT
            )
        """)

        # Inserăm cererea
        con.execute("""
            INSERT INTO inscrieri_concursuri
                (email, username, concurs, nume, data_nasterii, categorie_varsta, grad_centura, greutate, probe, gen)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (email, username, concurs, nume, data_nasterii, categorie_varsta, grad_centura, greutate, probe, gen))
        con.commit()

        return jsonify({"status": "success", "message": f"Cererea pentru „{concurs}” a fost trimisă!"}), 201

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
