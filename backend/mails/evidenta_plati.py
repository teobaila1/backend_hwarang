from flask import Blueprint, request, jsonify
from ..config import get_conn

evidenta_plati_bp = Blueprint("evidenta_plati", __name__)


def get_parinte_id_by_copil(copil_nume: str):
    """Găsește ID-ul părintelui căutând copilul în tabelul 'copii'."""
    if not copil_nume: return None
    target = copil_nume.strip().lower()
    con = get_conn()
    cur = con.cursor()
    # Căutare rapidă SQL
    cur.execute("SELECT id_parinte FROM copii WHERE LOWER(nume) = %s LIMIT 1", (target,))
    row = cur.fetchone()
    return row['id_parinte'] if row else None


@evidenta_plati_bp.get("/api/plati/filtrate")
def get_plati_filtrate():
    try:
        con = get_conn()
        cur = con.cursor()

        # 1. Luăm toate plățile înregistrate
        cur.execute("""
            SELECT p.*, u.username AS parinte_nume, COALESCE(u.nume_complet, u.username) AS parinte_display
            FROM plati p
            JOIN utilizatori u ON u.id = p.parinte_id
            ORDER BY p.id DESC
        """)
        plati_existente = [dict(r) for r in cur.fetchall()]

        # 2. Găsim copiii care NU au plăți (pentru a-i afișa cu roșu/neplătit)
        # Comparăm numele copilului din tabelul 'copii' cu numele din tabelul 'plati'

        # Luăm toți copiii din sistem
        cur.execute("""
            SELECT c.nume, u.username, COALESCE(u.nume_complet, u.username) as parinte_display
            FROM copii c
            JOIN utilizatori u ON c.id_parinte = u.id
        """)
        toti_copiii = cur.fetchall()

        copii_neplatiti = []
        for copil in toti_copiii:
            c_nume = (copil['nume'] or "").strip()
            if not c_nume: continue

            # Verificăm dacă există vreo plată pe acest nume
            # (Aici logica e simplistă pe nume, cum era înainte. Ideal ar fi pe ID, dar tabela plati nu are ID copil)
            has_payment = any(
                (p.get("copil_nume") or "").strip().lower() == c_nume.lower()
                for p in plati_existente
            )

            if not has_payment:
                copii_neplatiti.append({
                    "copil_nume": c_nume,
                    "parinte_nume": copil['username'],
                    "parinte_display": copil['parinte_display'],
                    "luna": None,
                    "suma": None,
                    "tip_plata": None,
                    "status": "neplatit"
                })

        return jsonify(plati_existente + copii_neplatiti)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.get("/api/plati")
def get_plati():
    try:
        con = get_conn()
        cur = con.cursor()
        cur.execute("""
            SELECT p.*, u.username AS parinte_nume, COALESCE(u.nume_complet, u.username) AS parinte_display
            FROM plati p
            JOIN utilizatori u ON u.id = p.parinte_id
            ORDER BY p.id DESC
        """)
        return jsonify([dict(r) for r in cur.fetchall()])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.post("/api/plati")
def add_plata():
    data = request.get_json(silent=True) or {}
    copil_nume = (data.get("copil_nume") or "").strip()
    luna = (data.get("luna") or "").strip().lower()
    suma = data.get("suma")
    tip_plata = data.get("tip_plata")
    status = data.get("status")

    if not copil_nume:
        return jsonify({"error": "Lipsește copil_nume"}), 400

    parinte_id = get_parinte_id_by_copil(copil_nume)
    if not parinte_id:
        return jsonify({"error": "Nu am putut identifica părintele acestui copil."}), 400

    try:
        con = get_conn()
        cur = con.cursor()

        # Update sau Insert
        cur.execute("""
            SELECT id FROM plati
            WHERE UPPER(copil_nume) = UPPER(%s) AND LOWER(luna) = LOWER(%s)
        """, (copil_nume, luna))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE plati SET suma=%s, tip_plata=%s, status=%s, parinte_id=%s WHERE id=%s
            """, (suma, tip_plata, status, parinte_id, existing["id"]))
        else:
            cur.execute("""
                INSERT INTO plati (parinte_id, copil_nume, luna, suma, tip_plata, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (parinte_id, copil_nume, luna, suma, tip_plata, status))

        con.commit()
        return jsonify({"message": "OK"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.put("/api/plati/<int:id>")
def update_plata(id):
    data = request.get_json(silent=True) or {}
    try:
        con = get_conn()
        cur = con.cursor()

        cur.execute("SELECT id FROM plati WHERE id = %s", (id,))
        if cur.fetchone():
            cur.execute("""
                UPDATE plati SET copil_nume=%s, luna=%s, suma=%s, tip_plata=%s, status=%s WHERE id=%s
            """, (data.get("copil_nume"), data.get("luna"), data.get("suma"),
                  data.get("tip_plata"), data.get("status"), id))
        else:
            # Fallback create
            parinte_id = get_parinte_id_by_copil(data.get("copil_nume"))
            if not parinte_id: return jsonify({"error": "Parinte necunoscut"}), 400
            cur.execute("""
                INSERT INTO plati (parinte_id, copil_nume, luna, suma, tip_plata, status)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (parinte_id, data.get("copil_nume"), data.get("luna"), data.get("suma"),
                  data.get("tip_plata"), data.get("status")))

        con.commit()
        return jsonify({"message": "OK"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@evidenta_plati_bp.delete("/api/plati/<int:id>")
def delete_plata(id):
    try:
        con = get_conn()
        con.execute("DELETE FROM plati WHERE id = %s", (id,))
        con.commit()
        return jsonify({"message": "Plată ștearsă"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500