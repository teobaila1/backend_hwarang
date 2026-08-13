from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
import jwt
import os
from backend.config import SECRET_KEY

status_bp = Blueprint('status', __name__)

# ATENȚIE: FĂRĂ @token_required la heartbeat!
@status_bp.route('/api/status/heartbeat', methods=['POST'])
def heartbeat():
    conn = None
    cursor = None
    try:
        data = request.json
        session_id = data.get('session_id')
        pagina = data.get('pagina', 'Acasa')
        
        if not session_id:
            return jsonify({"error": "No session ID"}), 400

        nume_utilizator = "Vizitator Anonim"
        token = request.headers.get('x-access-token')

        # Dacă vizitatorul are și un token (este logat), îi aflăm numele real
        if token:
            try:
                decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                # FIX: Am modificat din 'nume_club' în 'username'
                nume_utilizator = decoded.get('username', 'Utilizator Logat') 
            except Exception:
                pass # Dacă tokenul a expirat sau e invalid, rămâne vizitator anonim

        conn = get_conn()
        cursor = conn.cursor()
        
        # FIX: Folosim timpul specific pentru România direct din PostgreSQL
        query = """
            INSERT INTO online_users (session_id, nume_utilizator, ultima_activitate, pagina_curenta)
            VALUES (%s, %s, NOW() AT TIME ZONE 'Europe/Bucharest', %s)
            ON CONFLICT (session_id) 
            DO UPDATE SET 
                ultima_activitate = NOW() AT TIME ZONE 'Europe/Bucharest', 
                pagina_curenta = EXCLUDED.pagina_curenta,
                nume_utilizator = EXCLUDED.nume_utilizator;
        """
        cursor.execute(query, (session_id, nume_utilizator, pagina))
        conn.commit()
        return jsonify({"status": "alive"}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# Ruta pentru a CITI cine e online
@status_bp.route('/api/status/online', methods=['GET'])
@token_required 
def get_online_users():
    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # FIX: Folosim timpul României și formatăm data frumos pentru a fi trimisă în răspuns
        query = """
            SELECT 
                nume_utilizator, 
                pagina_curenta, 
                TO_CHAR(ultima_activitate, 'DD-MM-YYYY HH24:MI:SS') as ora_romaniei
            FROM online_users 
            WHERE ultima_activitate > (NOW() AT TIME ZONE 'Europe/Bucharest') - INTERVAL '1 minute'
            ORDER BY 
                CASE WHEN nume_utilizator = 'Vizitator Anonim' THEN 2 ELSE 1 END,
                ultima_activitate DESC
        """
        cursor.execute(query)
        users = cursor.fetchall()
        
        online_list = []
        for u in users:
            if isinstance(u, dict):
                # Dacă folosești psycopg2.extras.RealDictCursor
                online_list.append({
                    "nume": u.get("nume_utilizator"), 
                    "pagina": u.get("pagina_curenta"),
                    "ultima_activitate": u.get("ora_romaniei")
                })
            else:
                # Dacă folosești cursor normal (tuple)
                online_list.append({
                    "nume": u[0], 
                    "pagina": u[1],
                    "ultima_activitate": u[2]
                })
                
        return jsonify(online_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()