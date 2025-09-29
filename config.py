# config.py
import os
import sqlite3
from pathlib import Path

# 1) unde ținem DB:
#  - pe Render setăm ENV DB_PATH=/opt/render/project/src/users.db
#  - local, fallback la backend/users.db
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).with_name("users.db")))

def _ensure_db_exists():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        con = sqlite3.connect(DB_PATH)
        # ex: con.execute("CREATE TABLE IF NOT EXISTS utilizatori (...);")
        con.commit()
        con.close()

def get_conn():
    _ensure_db_exists()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con
