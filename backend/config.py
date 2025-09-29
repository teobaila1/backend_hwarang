import os, sqlite3
from pathlib import Path
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).with_name("users.db")))
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    return con
