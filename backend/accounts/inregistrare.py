import os
import json
import resend  # <--- IMPORT NOU
from datetime import datetime
from flask import Blueprint, request, jsonify
from threading import Thread  # <--- IMPORT NECESAR PENTRU VITEZĂ

from ..config import get_conn
from ..passwords.security import hash_password

# ELIMINĂM DEPENDENȚA DE emailer.py
# from ..mails.emailer import send_email_http

inregistrare_bp = Blueprint("inregistrare", __name__)

# Configurare Resend
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_IDENTITY = "ACS Hwarang Sibiu <site@hwarang.ro>"


# --- FUNCȚII EMAIL INTERNE ---

def _send_via_resend(destinatar, subiect, continut_html):
    """Trimite emailul efectiv prin Resend API."""
    try:
        # Verificare simplă
        if not resend.api_key:
            print("[MAIL ERROR] Lipseste RESEND_API_KEY")
            return

        r = resend.Emails.send({
            "from": SENDER_IDENTITY,
            "to": destinatar,
            "subject": subiect,
            "html": continut_html
        })
        print(f"[MAIL SENT] ID: {r.get('id')} -> {destinatar}")
    except Exception as e:
        print(f"[MAIL ERROR] {e}")


def trimite_email_confirmare(destinatar: str, username: str):
    html = f"""
        <p>Salut, {username}!</p>
        <p>Cererea ta de creare cont la <strong>ACS Hwarang Academy</strong> a fost înregistrată.</p>
        <p>Contul este <strong>în așteptare</strong>. Vei primi un email când un administrator îl aprobă.</p>
        <br><small>Echipa Hwarang</small>
    """
    _send_via_resend(destinatar, "Confirmare creare cont - ACS Hwarang", html)


def trimite_email_acceptare(destinatar: str, username: str):
    html = f"""
        <h2 style="color: green;">Cerere Acceptată!</h2>
        <p>Salut, {username}!</p>
        <p>Cererea ta a fost aprobată. Acum te poți autentifica pe site.</p>
        <a href="https://hwarang.ro/autentificare">Mergi la Login</a>
    """
    _send_via_resend(destinatar, "Cerere acceptată - ACS Hwarang", html)


def trimite_email_respingere(destinatar: str, username: str):
    html = f"""
        <h2 style="color: red;">Cerere Respinsă</h2>
        <p>Salut, {username}.</p>
        <p>Din păcate, cererea ta de creare cont a fost respinsă.</p>
    """
    _send_via_resend(destinatar, "Status Cerere - ACS Hwarang", html)


# --- UTILITARE ---

def _norm_gen(v):
    if v is None: return None
    s = str(v).strip().lower()
    if s in {"m", "masculin", "male", "b", "boy"}: return "M"
    if s in {"f", "feminin", "female", "g", "girl"}: return "F"
    return None


def _ensure_cereri_columns(con):
    try:
        cur = con.cursor()
        try:
            cur.execute("SELECT nume_complet, data_nasterii FROM cereri_utilizatori LIMIT 1")
        except:
            con.rollback()
            cur.execute("ALTER TABLE cereri_utilizatori ADD COLUMN IF NOT EXISTS nume_complet TEXT")
            cur.execute("ALTER TABLE cereri_utilizatori ADD COLUMN IF NOT EXISTS data_nasterii DATE")
            con.commit()
    except Exception as e:
        print(f"[WARN] Structura DB: {e}")
        con.rollback()


# --- RUTA PRINCIPALĂ ---

@inregistrare_bp.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}

    username = (data.get("username") or "").strip()
    full_name = (data.get("nume_complet") or "").strip()
    email = (data.get("email") or "").strip().lower()
    parola = data.get("password") or data.get("parola")
    tip = (data.get("tip") or "").strip()

    data_nasterii = data.get("data_nasterii") or None
    grupe_input = data.get("grupe", None)
    copii = data.get("copii", [])

    if not username or not email or not parola or not tip:
        return jsonify({"status": "error", "message": "Date incomplete."}), 400

    # Calcul vârstă
    varsta_calc = None
    if data_nasterii:
        try:
            by = int(str(data_nasterii).split("-")[0])
            varsta_calc = datetime.now().year - by
        except:
            pass

    # Validări simple
    tip_l = tip.lower()
    if tip_l == "sportiv" and not data_nasterii:
        return jsonify({"status": "error", "message": "Data nașterii obligatorie."}), 400

    # Procesare
    grupe_str = None
    copii_json = None

    if tip_l == "parinte":
        # ... logică procesare copii (prescurtată, e ok cum era) ...
        c_list = []
        g_set = set()
        for c in copii:
            nm = (c.get("nume") or "").strip()
            if not nm: continue
            gr = (c.get("grupa") or "").strip()
            if gr: g_set.add(gr)
            c_list.append({
                "nume": nm, "grupa": gr,
                "varsta": c.get("varsta"), "gen": _norm_gen(c.get("gen"))
            })
        if c_list:
            copii_json = json.dumps(c_list, ensure_ascii=False)
            grupe_str = ", ".join(sorted(g_set))
    else:
        grupe_str = grupe_input

    hashed = hash_password(parola)

    try:
        con = get_conn()
        _ensure_cereri_columns(con)
        cur = con.cursor()

        # Check duplicate
        for tab in ["cereri_utilizatori", "utilizatori"]:
            cur.execute(f"SELECT 1 FROM {tab} WHERE username=%s LIMIT 1", (username,))
            if cur.fetchone(): return jsonify({"status": "error", "message": "Username ocupat."}), 409
            cur.execute(f"SELECT 1 FROM {tab} WHERE email=%s LIMIT 1", (email,))
            if cur.fetchone(): return jsonify({"status": "error", "message": "Email ocupat."}), 409

        # Insert
        cur.execute("""
            INSERT INTO cereri_utilizatori
            (username, email, parola, tip, varsta, data_nasterii, copii, grupe, nume_complet)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (username, email, hashed, tip, varsta_calc, data_nasterii, copii_json, grupe_str, full_name))
        con.commit()

        # --- TRIMITERE EMAIL ASINCRON (FIX) ---
        def run_mail():
            trimite_email_confirmare(email, username)

        Thread(target=run_mail).start()
        # -------------------------------------

        return jsonify({"status": "success"}), 200

    except Exception as e:
        if con: con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500