# backend/document/upload_document.py
import os
from pathlib import Path
from datetime import datetime
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from ..config import get_conn

upload_document_bp = Blueprint('upload_document', __name__)

# <rădăcina proiectului>/uploads
ROOT_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = ROOT_DIR / "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------- DB helpers ----------------
def _ensure_table_exists():
    con = get_conn()
    con.execute("""
        CREATE TABLE IF NOT EXISTS documente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename   TEXT NOT NULL,
            uploaded_by TEXT,
            upload_date TEXT
        )
    """)
    con.commit()
    _migrate_if_needed()  # asigură PK pe 'id'


def _migrate_if_needed():
    """
    Dacă 'id' nu e PRIMARY KEY INTEGER, recreează tabela corect și copiază datele.
    (CREATE TABLE IF NOT EXISTS nu face migrare.)
    """
    con = get_conn()
    info = con.execute("PRAGMA table_info(documente)").fetchall()
    cols = {row[1]: row for row in info}  # (cid, name, type, notnull, dflt_value, pk)

    id_ok = False
    if "id" in cols:
        id_type = (cols["id"][2] or "").upper()
        id_pk = cols["id"][5] == 1
        id_ok = id_type.startswith("INTEGER") and id_pk

    if not id_ok:
        con.execute("BEGIN")
        con.execute("""
            CREATE TABLE IF NOT EXISTS documente_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename   TEXT NOT NULL,
                uploaded_by TEXT,
                upload_date TEXT
            )
        """)
        # copiem datele (id-urile vor fi regenerate automat)
        con.execute("""
            INSERT INTO documente_new (filename, uploaded_by, upload_date)
            SELECT filename, uploaded_by, upload_date FROM documente
        """)
        con.execute("DROP TABLE documente")
        con.execute("ALTER TABLE documente_new RENAME TO documente")
        con.commit()


def _unique_filename(dest_dir: Path, filename: str) -> str:
    """Evită coliziunile: foo.pdf, foo(1).pdf, foo(2).pdf …"""
    filename = secure_filename(filename) or "upload"
    base, ext = os.path.splitext(filename)
    cand = filename
    i = 1
    while (dest_dir / cand).exists():
        cand = f"{base}({i}){ext}"
        i += 1
    return cand


def _get_filename_by_id(doc_id: int):
    con = get_conn()
    row = con.execute("SELECT filename FROM documente WHERE id = ?", (doc_id,)).fetchone()
    return (row["filename"] if row else None)
# -------------------------------------------


# --------------- Endpoints -----------------
@upload_document_bp.post('/api/upload_document')
def upload_documents():
    """
    Primește FormData:
      - files[]: fișierele
      - username: cine încarcă
    Returnează: { status, saved: [{id, filename}, ...] }
    """
    files = request.files.getlist('files')
    username = (request.form.get('username') or "").strip()

    if not files or not username:
        return jsonify({'status': 'error', 'message': 'Missing files or username'}), 400

    try:
        _ensure_table_exists()
        con = get_conn()

        saved = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for file in files:
            if not file or not file.filename:
                continue

            safe_name = _unique_filename(UPLOAD_DIR, file.filename)
            file.save(UPLOAD_DIR / safe_name)

            cur = con.execute(
                'INSERT INTO documente (filename, uploaded_by, upload_date) VALUES (?, ?, ?)',
                (safe_name, username, now)
            )
            doc_id = cur.lastrowid  # <<— ID-ul real, generat de SQLite
            saved.append({"id": doc_id, "filename": safe_name})

        con.commit()

        if not saved:
            return jsonify({'status': 'error', 'message': 'No valid files received'}), 400

        return jsonify({'status': 'success', 'saved': saved}), 201

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@upload_document_bp.get('/api/uploads/id/<int:doc_id>')
def download_file_by_id(doc_id):
    filename = _get_filename_by_id(doc_id)
    if not filename:
        return jsonify({'status': 'error', 'message': 'Document inexistent'}), 404
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@upload_document_bp.get('/api/get_documents')
def get_documents():
    try:
        _ensure_table_exists()
        con = get_conn()
        docs = con.execute("""
            SELECT id,
                   filename,
                   COALESCE(uploaded_by, '') AS uploaded_by,
                   COALESCE(upload_date,  '') AS upload_date
            FROM documente
            ORDER BY datetime(upload_date) DESC, id DESC
        """).fetchall()

        return jsonify([
            {
                "id": r["id"],
                "filename": r["filename"],
                "uploaded_by": r["uploaded_by"],
                "upload_date": r["upload_date"],
                "download_url": f"/api/uploads/id/{r['id']}"
            } for r in docs
        ])
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@upload_document_bp.delete('/api/delete_document/id/<int:doc_id>')
def delete_document_by_id(doc_id):
    filename = _get_filename_by_id(doc_id)
    if not filename:
        return jsonify({'status': 'error', 'message': 'Document inexistent'}), 404

    try:
        # șterge din disc
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            os.remove(file_path)

        # șterge din DB
        con = get_conn()
        con.execute('DELETE FROM documente WHERE id = ?', (doc_id,))
        con.commit()
        return jsonify({'status': 'success', 'message': f'id {doc_id} șters cu succes'}), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
# -------------------------------------------
