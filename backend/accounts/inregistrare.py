import os
import json
from datetime import datetime
from flask import Blueprint, request, jsonify

from ..config import get_conn
from ..passwords.security import hash_password
from ..mails.emailer import send_email_http

inregistrare_bp = Blueprint("inregistrare", __name__)


# --- FUNCȚII EMAIL (PĂSTRATE) ---

def trimite_email_confirmare(destinatar: str, username: str):
    subject = "Confirmare creare cont - ACS Hwarang Academy Sibiu"
    text = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont la ACS Hwarang Academy a fost înregistrată cu succes.\n"
        "Te vom contacta după aprobare."
    )
    html = f"""
        <p>Bună, {username}!</p>
        <p>Cererea ta de creare cont la <strong>ACS Hwarang Academy</strong> a fost
        înregistrată cu succes.</p>
        <p>Te vom contacta după aprobare.</p>
    """
    send_email_http(destinatar, subject, html, text)


def trimite_email_acceptare(destinatar: str, username: str):
    subject = "Cerere acceptată - ACS Hwarang Academy"
    text = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont a fost ACCEPTATĂ.\n"
        "Te poți autentifica pe site-ul ACS Hwarang Academy."
    )
    html = f"""
        <p>Bună, {username}!</p>
        <p>Cererea ta de creare cont a fost <strong>ACCEPTATĂ</strong>.</p>
        <p>Te poți autentifica pe site-ul <strong>ACS Hwarang Academy</strong>.</p>
    """
    send_email_http(destinatar, subject, html, text)


def trimite_email_respingere(destinatar: str, username: str):
    subject = "Cerere respinsă - ACS Hwarang Academy"
    text = (
        f"Bună, {username}!\n\n"
        "Cererea ta de creare cont a fost RESPINSĂ.\n"
        "Dacă ai întrebări, te rugăm să ne contactezi."
    )
    html = f"""
        <p>Bună, {username}!</p>
        <p>Cererea ta de creare cont a fost <strong>RESPINSĂ</strong>.</p>
        <p>Dacă ai întrebări, te rugăm să ne contactezi.</p>
    """
    send_email_http(destinatar, subject, html, text)


# --- UTILITARE ---

def _norm_gen(v):
    """Normalizează diverse forme în 'M' / 'F' sau None."""
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"m", "masculin", "male", "b", "boy"}:
        return "M"
    if s in {"f", "feminin", "female", "g", "girl"}:
        return "F"
    return None


def _ensure_cereri_columns(con):
    """
    Se asigură că tabelul cereri_utilizatori are coloanele noi
    necesare pentru migrarea la structura SQL.
    """
    try:
        cur = con.cursor()
        # Încercăm să selectăm coloanele noi. Dacă dă eroare, le creăm.
        try:
            cur.execute("SELECT nume_complet, data_nasterii FROM cereri_utilizatori LIMIT 1")
        except:
            con.rollback()
            cur.execute("ALTER TABLE cereri_utilizatori ADD COLUMN IF NOT EXISTS nume_complet TEXT")
            cur.execute("ALTER TABLE cereri_utilizatori ADD COLUMN IF NOT EXISTS data_nasterii DATE")
            con.commit()
    except Exception as e:
        print(f"[WARN] Eroare la verificarea coloanelor cereri: {e}")
        con.rollback()


# --- RUTA PRINCIPALĂ ---

@inregistrare_bp.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    full_name = (data.get("nume_complet") or "").strip()
    email = (data.get("email") or "").strip().lower()
    parola = data.get("password") or data.get("parola")
    tip = (data.get("tip") or "").strip()  # Rolul: 'Parinte', 'Sportiv', 'Antrenor'

    # Data nașterii (obligatorie pentru Sportiv/Antrenor în noua structură)
    data_nasterii = data.get("data_nasterii")
    if not data_nasterii:
        data_nasterii = None

    grupe_input = data.get("grupe", None)
    copii = data.get("copii", [])

    if not username or not email or not parola or not tip:
        return jsonify({"status": "error", "message": "Toate câmpurile de bază sunt obligatorii"}), 400

    tip_l = tip.lower()

    # --- CALCUL VÂRSTĂ (Pentru afișare rapidă în Admin) ---
    varsta_calc = None
    if data_nasterii:
        try:
            # Data vine format "YYYY-MM-DD"
            birth_year = int(str(data_nasterii).split("-")[0])
            current_year = datetime.now().year
            varsta_calc = current_year - birth_year
        except:
            varsta_calc = None

    # --- VALIDĂRI SPECIFICE ---

    # 1. Validare SPORTIV
    if tip_l == "sportiv":
        if not data_nasterii:
            return jsonify({"status": "error", "message": "Data nașterii este obligatorie pentru sportiv"}), 400
        if not grupe_input:
            return jsonify({"status": "error", "message": "Te rugăm să specifici grupa din care faci parte."}), 400

    # 2. Validare ANTRENOR
    elif tip_l == "antrenor":
        if not grupe_input:
            return jsonify(
                {"status": "error", "message": "Specificarea grupelor este obligatorie pentru antrenor."}), 400
        if not data_nasterii:
            return jsonify({"status": "error", "message": "Data nașterii este obligatorie pentru antrenor"}), 400

    # --- PROCESARE DATE ---

    grupe_str = None
    copii_json = None

    # A. Procesare PĂRINTE (Copii)
    if tip_l == "parinte":
        grupe_set = set()
        copii_curati = []
        for c in (copii or []):
            nume_c = (c.get("nume") or "").strip()
            grupa_c = (c.get("grupa") or "").strip()
            # La register simplu, de multe ori vine doar vârsta, nu data nașterii copilului.
            # E ok, adminul poate completa sau cerem în formular.
            varsta_c = c.get("varsta")
            gen_c = _norm_gen(c.get("gen"))

            if not nume_c: continue

            if grupa_c:
                grupe_set.add(grupa_c)

            # Normalizare vârstă
            if isinstance(varsta_c, str) and varsta_c.isdigit():
                varsta_c = int(varsta_c)

            copii_curati.append({
                "nume": nume_c,
                "grupa": grupa_c,
                "varsta": varsta_c,
                "gen": gen_c
            })

        if copii_curati:
            # Salvăm copiii ca JSON temporar în cereri.
            # La acceptare, acest JSON va fi transformat în rânduri în tabelul 'copii'.
            copii_json = json.dumps(copii_curati, ensure_ascii=False)

            # Salvăm și o listă text a grupelor pentru referință rapidă
            grupe_str = ", ".join(sorted(g for g in grupe_set if g)) or None

    # B. Procesare SPORTIV/ANTRENOR (Grupe)
    else:
        # Păstrăm grupele ca string. La acceptare vor fi legate în tabelul 'sportivi_pe_grupe'.
        grupe_str = (grupe_input or None)

    hashed_parola = hash_password(parola)

    try:
        con = get_conn()
        _ensure_cereri_columns(con)  # Asigură structura

        cur = con.cursor()

        # Verificări unicitate (Cereri + Useri existenți)
        cur.execute("SELECT 1 FROM cereri_utilizatori WHERE username = %s LIMIT 1", (username,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Username deja folosit (în așteptare)"}), 409

        cur.execute("SELECT 1 FROM utilizatori WHERE username = %s LIMIT 1", (username,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Username deja folosit"}), 409

        cur.execute("SELECT 1 FROM cereri_utilizatori WHERE email = %s LIMIT 1", (email,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Email deja folosit (în așteptare)"}), 409

        cur.execute("SELECT 1 FROM utilizatori WHERE email = %s LIMIT 1", (email,))
        if cur.fetchone(): return jsonify({"status": "error", "message": "Email deja folosit"}), 409

        # Inserare în CERERI_UTILIZATORI
        # Salvăm 'tip' (care va deveni 'rol' la acceptare)
        cur.execute(
            """
            INSERT INTO cereri_utilizatori
                (username, email, parola, tip, varsta, data_nasterii, copii, grupe, nume_complet)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (username, email, hashed_parola, tip, varsta_calc, data_nasterii, copii_json, grupe_str, full_name),
        )
        con.commit()

    except Exception as e:
        return jsonify({"status": "error", "message": f"Eroare server: {str(e)}"}), 500

    # Trimitere email confirmare
    try:
        trimite_email_confirmare(email, username)
    except Exception as e:
        print("[WARN] Email confirmare a eșuat:", e)

    return jsonify({"status": "success"}), 200