import os
from pathlib import Path
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

# Postgres (Render)
DATABASE_URL = os.getenv("DATABASE_URL")

# Fallback pentru local dev (dacă vrei să mai rulezi pe sqlite)
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).with_name("users.db")))


class DBConn:
    """
    Wrapper peste conexiune astfel încât:
    - să poți folosi con.execute("...", params) ca la sqlite
    - să poți folosi con.cursor() ca la psycopg2
    - să meargă 'with get_conn() as con: ...'
    """

    def __init__(self, raw_conn):
        self._raw = raw_conn

    # --- context manager ---------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type:
                self._raw.rollback()
            else:
                self._raw.commit()
        finally:
            self._raw.close()

    # --- API compatibil sqlite ---------------------------------------------
    def execute(self, sql: str, params=None):
        """
        Permite codului vechi să facă:
            con.execute("SELECT ... WHERE x = ?", (val,))
        și traduce automat `?` ➜ `%s` pentru Postgres.
        Returnează cursorul, ca la sqlite3.
        """
        if "?" in sql:
            sql = sql.replace("?", "%s")

        cur = self._raw.cursor()
        cur.execute(sql, params or ())
        return cur

    def cursor(self, *args, **kwargs):
        return self._raw.cursor(*args, **kwargs)

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


def _connect_postgres() -> DBConn:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL nu este setat. Adaugă-l în Environment-ul serviciului de backend."
        )
    raw = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return DBConn(raw)


def _connect_sqlite() -> DBConn:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH)
    raw.row_factory = sqlite3.Row
    return DBConn(raw)


def get_conn() -> DBConn:
    """
    - În producție (Render): folosește Postgres (DATABASE_URL setat)
    - Local, fără DATABASE_URL: cade pe sqlite (users.db), ca înainte
    """
    if DATABASE_URL:
        return _connect_postgres()
    return _connect_sqlite()
