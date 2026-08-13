from flask import Blueprint, request, jsonify
from backend.config import get_conn
from backend.accounts.decorators import token_required
import jwt
import os

from backend.config import SECRET_KEY

status_bp = Blueprint('status', __name__)

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

        if token:
            try:
                decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                nume_utilizator = decoded.get('username', 'Utilizator Logat') 
            except Exception:
                pass 

        conn = get_conn()
        cursor = conn.cursor()
        
        # 1. Update tabel online curent
        query_online = """
            INSERT INTO online_users (session_id, nume_utilizator, ultima_activitate, pagina_curenta)
            VALUES (%s, %s, NOW() AT TIME ZONE 'Europe/Bucharest', %s)
            ON CONFLICT (session_id) 
            DO UPDATE SET 
                ultima_activitate = NOW() AT TIME ZONE 'Europe/Bucharest', 
                pagina_curenta = EXCLUDED.pagina_curenta,
                nume_utilizator = EXCLUDED.nume_utilizator;
        """
        cursor.execute(query_online, (session_id, nume_utilizator, pagina))

        # 2. Logică pentru ISTORIC (Inserăm doar dacă pagina s-a schimbat)
        cursor.execute("""
            SELECT pagina_accesata 
            FROM istoric_navigare 
            WHERE session_id = %s 
            ORDER BY data_accesare DESC 
            LIMIT 1
        """, (session_id,))
        
        last_page_row = cursor.fetchone()
        last_page = last_page_row[0] if last_page_row else None

        if last_page != pagina:
            cursor.execute("""
                INSERT INTO istoric_navigare (session_id, nume_utilizator, pagina_accesata, data_accesare)
                VALUES (%s, %s, %s, NOW() AT TIME ZONE 'Europe/Bucharest')
            """, (session_id, nume_utilizator, pagina))

        conn.commit()
        return jsonify({"status": "alive"}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# RUTA NOUĂ PENTRU ADMINI - ISTORIC
@status_bp.route('/api/status/istoric', methods=['GET'])
@token_required 
def get_istoric_navigare():
    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # Extragem ultimele 200 de acțiuni, ordonate de la cea mai recentă
        query = """
            SELECT 
                session_id,
                nume_utilizator, 
                pagina_accesata, 
                TO_CHAR(data_accesare, 'DD-MM-YYYY HH24:MI:SS') as ora_romaniei
            FROM istoric_navigare 
            ORDER BY data_accesare DESC
            LIMIT 200
        """
        cursor.execute(query)
        users = cursor.fetchall()
        
        istoric_list = []
        for u in users:
            if isinstance(u, dict):
                istoric_list.append({
                    "session_id": u.get("session_id"),
                    "nume": u.get("nume_utilizator"), 
                    "pagina": u.get("pagina_accesata"),
                    "data": u.get("ora_romaniei")
                })
            else:
                istoric_list.append({
                    "session_id": u[0],
                    "nume": u[1], 
                    "pagina": u[2],
                    "data": u[3]
                })
                
        return jsonify(istoric_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()