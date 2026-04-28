import os
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from ..config import get_conn
from ..accounts.decorators import token_required, admin_required  # <--- IMPORTURI ESENȚIALE

upload_document_bp = Blueprint("upload_document", __name__)

# <rădăcina proiectului>/uploads
ROOT_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = ROOT_DIR / "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------- DB helpers ----------------
def _unique_filename(dest_dir: Path, filename: str) -> str:
    """
    Evită coliziunile: foo.pdf, foo(1).pdf, foo(2).pdf …
    """
    filename = secure_filename(filename) or "upload"
    base, ext = os.path.splitext(filename)
    cand = filename
    i = 1
    while (dest_dir / cand).exists():
        cand = f"{base}({i}){ext}"
        i += 1
    return cand


def _get_filename_by_id(doc_id: int):
    """
    Returnează filename pentru un id din tabela `documente`,
    sau None dacă nu există.
    """
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                cur.execute("SELECT filename FROM documente WHERE id = %s", (doc_id,))
                row = cur.fetchone()
                # Tratare diferită în funcție de driver (dict sau tuple)
                if row:
                    if isinstance(row, dict):
                        return row["filename"]
                    return row[0]
    except Exception:
        pass
    return None


# ---------------- RUTE ----------------

@upload_document_bp.post("/api/upload_document")
@token_required  # <--- Doar utilizatorii logați pot încărca
def upload_documents():
    # Verificăm dacă există partea de fișiere
    if "files" not in request.files:
        return jsonify({"status": "error", "message": "Nu au fost trimise fișiere."}), 400

    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"status": "error", "message": "Niciun fișier selectat."}), 400

    # Preluăm username-ul
    username = "Anonim"
    if hasattr(request, 'user_data'):
        username = request.user_data.get('username', 'Anonim')
    else:
        username = request.form.get("username", "Anonim")

    saved_count = 0
    con = get_conn()

    try:
        # Blocul 'with' deschide conexiunea și face 'commit' automat la final!
        with con:
            with con.cursor() as cur:
                # Asigurăm tabela
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS documente (
                        id SERIAL PRIMARY KEY,
                        filename TEXT NOT NULL,
                        uploaded_by TEXT,
                        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                for f in files:
                    if f and f.filename:
                        # 1. Generăm nume unic pe disk
                        safe_name = _unique_filename(UPLOAD_DIR, f.filename)
                        save_path = UPLOAD_DIR / safe_name

                        # 2. Salvăm fizic (am pus str() pt siguranță maximă)
                        f.save(str(save_path))

                        # 3. Salvăm în baza de date
                        cur.execute(
                            "INSERT INTO documente (filename, uploaded_by) VALUES (%s, %s)",
                            (safe_name, username)
                        )
                        saved_count += 1
                        
        # AM ȘTERS con.commit() DE AICI! 
        
        return jsonify({"status": "success", "message": f"{saved_count} fișiere încărcate."}), 201

    except Exception as e:
        print("EROARE FATALĂ LA UPLOAD:")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Eroare internă de server."}), 500


import traceback # Adaugă asta sus de tot în fișier (dacă nu ai deja)

@upload_document_bp.get("/api/get_documents")
@token_required  # <--- Doar cei logați văd lista
def get_documents():
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                # Verificăm dacă tabela există
                cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'documente')")
                row = cur.fetchone()
                
                table_exists = False
                if row:
                    table_exists = row['exists'] if isinstance(row, dict) else row[0]
                    
                if not table_exists:
                    return jsonify([])

                # FIX-UL AICI: Selectăm upload_date simplu, fără TO_CHAR
                cur.execute("""
                    SELECT id, filename, uploaded_by, upload_date 
                    FROM documente 
                    ORDER BY id DESC
                """)
                rows = cur.fetchall()

        docs = []
        for r in rows:
            # Gestionare tuplu vs dict + transformare sigură în string a datei
            if isinstance(r, dict):
                docs.append({
                    "id": r["id"],
                    "filename": r["filename"],
                    "uploaded_by": r["uploaded_by"],
                    "upload_date": str(r["upload_date"]) if r["upload_date"] else "-",
                    "download_url": f"/api/uploads/id/{r['id']}",
                })
            else:
                docs.append({
                    "id": r[0],
                    "filename": r[1],
                    "uploaded_by": r[2],
                    "upload_date": str(r[3]) if r[3] else "-",
                    "download_url": f"/api/uploads/id/{r[0]}",
                })

        return jsonify(docs)

    except Exception as e:
        print("EROARE FATALĂ IN get_documents:")
        import traceback
        traceback.print_exc() 
        return jsonify({"status": "error", "message": "Eroare internă de server."}), 500


@upload_document_bp.get("/api/uploads/id/<int:doc_id>")
@token_required  # <--- Doar cei logați descarcă
def download_file_by_id(doc_id):
    filename = _get_filename_by_id(doc_id)
    if not filename:
        return jsonify({"status": "error", "message": "Documentul nu există în baza de date."}), 404

    # Verificăm dacă fișierul fizic a supraviețuit deploy-ului Render
    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        return jsonify({
            "status": "error", 
            "message": "Fișierul fizic nu mai există pe server (șters de Render la deploy)."
        }), 404

    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@upload_document_bp.delete("/api/delete_document/id/<int:doc_id>")
@token_required
@admin_required  # <--- Doar ADMIN șterge
def delete_document_by_id(doc_id):
    try:
        filename = _get_filename_by_id(doc_id)
        if not filename:
            return jsonify({"status": "error", "message": "Document inexistent în DB"}), 404

        # 1. Ștergem fizic DOAR dacă mai există
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            os.remove(file_path)

        # 2. Ștergem din DB (chiar dacă fișierul fizic dispăruse, vrem să curățăm lista)
        con = get_conn()
        with con:
            with con.cursor() as cur:
                cur.execute("DELETE FROM documente WHERE id = %s", (doc_id,))
        
        return jsonify({"status": "success", "message": "Document șters cu succes!"}), 200

    except Exception as e:
        print(f"EROARE FATALĂ LA ȘTERGEREA DOC ID {doc_id}:")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Eroare internă de server."}), 500