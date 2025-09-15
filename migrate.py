# # migrate_passwords.py (rulezi o singură dată)
# import sqlite3
# from backend.passwords.security import hash_password
#
# conn = sqlite3.connect("../users.db")
# conn.row_factory = sqlite3.Row
# rows = conn.execute("SELECT id, parola FROM utilizatori").fetchall()
#
# for r in rows:
#     p = r["parola"]
#     if p is None:
#         continue
#     if isinstance(p, (bytes, bytearray)):
#         p = p.decode("utf-8", "ignore")
#     p = str(p)
#     if not p.startswith("pbkdf2:"):  # nu e hash werkzeug -> probabil plaintext
#         conn.execute("UPDATE utilizatori SET parola=? WHERE id=?", (hash_password(p), r["id"]))
#
# conn.commit()
# conn.close()
# print("Migrare parole: OK")



import sqlite3, pathlib

DB_PATH = pathlib.Path(r"C:\Users\Teo\Desktop\Site_Hwarang\vite_hwarang_react\backend\users.db")
sql = pathlib.Path("migration_utilizatori_autoincrement.sql").read_text(encoding="utf-8")

con = sqlite3.connect(DB_PATH)
try:
    con.executescript(sql)
    con.commit()
    print("Migrare OK.")
finally:
    con.close()
