import json
from datetime import datetime
from flask import Blueprint, request, jsonify
from ..config import get_conn
from ..accounts.decorators import token_required

inscriere_concurs_bp = Blueprint('inscriere_concurs', __name__)


@inscriere_concurs_bp.post('/api/inscriere_concurs')
@token_required
def inscriere_concurs():
    data = request.get_json(silent=True) or {}

    # Datele vin din frontend
    username = data.get('username')
    nume_concurs = data.get('concurs')
    nume_sportiv = data.get('nume')
    data_nasterii = data.get('dataNasterii')
    categorie = data.get('categorieVarsta')
    grad = data.get('gradCentura')
    greutate = data.get('greutate')
    inaltime = data.get('inaltime')
    probe = data.get('probe')
    gen = data.get('gen')

    # Validări minime
    if not all([username, nume_concurs, nume_sportiv, probe]):
        return jsonify({"status": "error", "message": "Date incomplete."}), 400

    try:
        con = get_conn()
        cur = con.cursor()

        # Inserăm în tabelul inscrieri (presupunând că există și are structura asta)
        # NOTĂ: Aici nu s-a schimbat nimic în baza de date la concursuri, deci inserarea e standard.
        # Singura chestie e că frontend-ul trimite datele gata completate.

        # Verificăm duplicat
        cur.execute("""
            SELECT id FROM inscrieri 
            WHERE concurs = %s AND nume_sportiv = %s
        """, (nume_concurs, nume_sportiv))

        if cur.fetchone():
            return jsonify({"status": "error", "message": "Sportivul este deja înscris la acest concurs."}), 409

        cur.execute("""
            INSERT INTO inscrieri (
                username_parinte, concurs, nume_sportiv, data_nasterii, 
                categorie, grad, greutate, inaltime, probe, gen, data_inscriere
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (username, nume_concurs, nume_sportiv, data_nasterii, categorie, grad, greutate, inaltime, probe, gen))

        con.commit()
        return jsonify({"status": "success", "message": "Înscriere reușită!"}), 201

    except Exception as e:
        con.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500