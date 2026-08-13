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
        
        # Prelucrăm automat datele tehnice
        # 1. Adresa IP (X-Forwarded-For este necesar pentru servere cloud/proxy-uri)
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()
            
        # 2. Dispozitivul/Browserul
        device = request.headers.get('User-Agent', 'Necunoscut')
        
        # 3. Referrer-ul (de unde a venit). Îl luăm din frontend dacă e trimis, altfel din headere
        referrer = data.get('referrer', request.headers.get('Referer', 'Direct / Fără Sursă'))

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
        
        # --- UPDATE UTILIZATORI ONLINE ---
        query_online = """
            INSERT INTO online_users (session_id, nume_utilizator, ultima_activitate, pagina_curenta, ip, device, referrer)
            VALUES (%s, %s, NOW() AT TIME ZONE 'Europe/Bucharest', %s, %s, %s, %s)
            ON CONFLICT (session_id) 
            DO UPDATE SET 
                ultima_activitate = NOW() AT TIME ZONE 'Europe/Bucharest', 
                pagina_curenta = EXCLUDED.pagina_curenta,
                nume_utilizator = EXCLUDED.nume_utilizator,
                ip = EXCLUDED.ip,
                device = EXCLUDED.device,
                referrer = EXCLUDED.referrer;
        """
        cursor.execute(query_online, (session_id, nume_utilizator, pagina, ip_address, device, referrer))

        # --- UPDATE ISTORIC (Doar dacă a schimbat pagina) ---
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
                INSERT INTO istoric_navigare (session_id, nume_utilizator, pagina_accesata, data_accesare, ip, device, referrer)
                VALUES (%s, %s, %s, NOW() AT TIME ZONE 'Europe/Bucharest', %s, %s, %s)
            """, (session_id, nume_utilizator, pagina, ip_address, device, referrer))

        conn.commit()
        return jsonify({"status": "alive"}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@status_bp.route('/api/status/istoric', methods=['GET'])
@token_required 
def get_istoric_navigare():
    conn = None
    cursor = None
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        # Extragem tot, inclusiv noile date tehnice
        query = """
            SELECT 
                session_id,
                nume_utilizator, 
                pagina_accesata, 
                TO_CHAR(data_accesare, 'DD-MM-YYYY HH24:MI:SS') as ora_romaniei,
                ip,
                device,
                referrer
            FROM istoric_navigare 
            ORDER BY data_accesare DESC
            LIMIT 300
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
                    "data": u.get("ora_romaniei"),
                    "ip": u.get("ip"),
                    "device": u.get("device"),
                    "sursa": u.get("referrer")
                })
            else:
                istoric_list.append({
                    "session_id": u[0],
                    "nume": u[1], 
                    "pagina": u[2],
                    "data": u[3],
                    "ip": u[4],
                    "device": u[5],
                    "sursa": u[6]
                })
                
        return jsonify(istoric_list), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()