from pathlib import Path
import sqlite3

# pune EXACT calea către fișierul care chiar are tabela 'utilizatori'
DB_PATH = Path(r"C:\Users\Teo\Desktop\Site_Hwarang\vite_hwarang_react\backend\users.db")

def get_conn():
    # Deschide în modul read-write existent (NU creează automat DB). Dacă calea e greșită, aruncă eroare.
    uri = f"file:{DB_PATH.as_posix()}?mode=rw"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con
