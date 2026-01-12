# backend/document/upload_document.py
import os
from pathlib import Path
from datetime import datetime

from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from ..accounts.decorators import admin_required
from ..config import get_conn

from ..accounts.decorators import token_required, admin_required # <-- IMPORT

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
                cur.execute(
                    "SELECT filename FROM documente WHERE id = %s",
                    (doc_id,),
                )
                row = cur.fetchone()
                return row["filename"] if row else None
    finally:
        con.close()
# -------------------------------------------


# --------------- Endpoints -----------------
@upload_document_bp.post("/api/upload_document")
@admin_required  # <-- Doar userii logați pot încărca
def upload_documents():
    """
    Primește FormData:
      - files[]: fișierele
      - username: cine încarcă

    Returnează: { status, saved: [{id, filename}, ...] }
    """
    files = request.files.getlist("files")
    username = (request.form.get("username") or "").strip()

    if not files or not username:
        return (
            jsonify({"status": "error", "message": "Missing files or username"}),
            400,
        )

    con = get_conn()
    saved = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with con:
            with con.cursor() as cur:
                for file in files:
                    if not file or not file.filename:
                        continue

                    safe_name = _unique_filename(UPLOAD_DIR, file.filename)
                    file.save(UPLOAD_DIR / safe_name)

                    # Postgres: folosim %s și RETURNING id ca să luăm PK-ul generat
                    cur.execute(
                        """
                        INSERT INTO documente (filename, uploaded_by, upload_date)
                        VALUES (%s, %s, %s)
                        RETURNING id
                        """,
                        (safe_name, username, now),
                    )
                    row = cur.fetchone()
                    doc_id = row["id"] if row else None
                    saved.append({"id": doc_id, "filename": safe_name})

        if not saved:
            return (
                jsonify({"status": "error", "message": "No valid files received"}),
                400,
            )

        return jsonify({"status": "success", "saved": saved}), 201

    except Exception as e:
        # în caz de eroare, conexiunea iese din with și face rollback
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


@upload_document_bp.get("/api/uploads/id/<int:doc_id>")
@token_required # <-- Doar cei logați pot descărca
def download_file_by_id(doc_id):
    filename = _get_filename_by_id(doc_id)
    if not filename:
        return jsonify({"status": "error", "message": "Document inexistent"}), 404
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@upload_document_bp.get("/api/get_documents")
@token_required # <-- Doar cei logați văd lista
def get_documents():
    """
    Returnează lista documentelor, ordonate descrescător după data upload-ului.

    upload_date în DB este text în format 'YYYY-MM-DD HH:MI:SS'.
    În Postgres îl sortăm folosind cast la timestamp, și tratăm stringul gol
    ca NULL ca să nu dea eroare la cast.
    """
    con = get_conn()
    try:
        with con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        filename,
                        COALESCE(uploaded_by, '') AS uploaded_by,
                        COALESCE(upload_date, '') AS upload_date
                    FROM documente
                    ORDER BY
                        NULLIF(upload_date, '')::timestamp DESC NULLS LAST,
                        id DESC
                    """
                )
                rows = cur.fetchall()

        docs = [
            {
                "id": r["id"],
                "filename": r["filename"],
                "uploaded_by": r["uploaded_by"],
                "upload_date": r["upload_date"],
                "download_url": f"/api/uploads/id/{r['id']}",
            }
            for r in rows
        ]
        return jsonify(docs)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()


@upload_document_bp.delete("/api/delete_document/id/<int:doc_id>")
@token_required
@admin_required # <-- Doar ADMINII pot șterge
def delete_document_by_id(doc_id):
    filename = _get_filename_by_id(doc_id)
    if not filename:
        return jsonify({"status": "error", "message": "Document inexistent"}), 404

    con = get_conn()
    try:
        # ștergem din disc
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            os.remove(file_path)

        # ștergem din DB
        with con:
            with con.cursor() as cur:
                cur.execute("DELETE FROM documente WHERE id = %s", (doc_id,))

        return (
            jsonify(
                {"status": "success", "message": f"id {doc_id} șters cu succes"}
            ),
            200,
        )

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        con.close()
# -------------------------------------------
