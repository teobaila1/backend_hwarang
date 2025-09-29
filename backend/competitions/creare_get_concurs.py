from flask import Blueprint, jsonify
from ..config import get_conn, DB_PATH
from datetime import date

creare_get_concurs_bp = Blueprint('creare_get_concurs', __name__)

def extract_data_start(perioada: str):
    """
    Suportă exemple:
      - "12–14.09.2025"  -> 2025-09-12
      - "12-14.09.2025"  -> 2025-09-12
      - "12–14.09"       -> <an curent>-09-12
      - "12.09.2025"     -> 2025-09-12
      - "12.09"          -> <an curent>-09-12
    Returnează string ISO YYYY-MM-DD sau None dacă nu poate parsa.
    """
    if not perioada:
        return None

    s = str(perioada).strip()
    cur_year = date.today().year
    dash = "–" if "–" in s else ("-" if "-" in s else None)

    try:
        if dash:
            left, right = s.split(dash, 1)
            day_start = left.strip().split(".")[0]  # "12"
            parts = right.strip().split(".")
            # right poate fi: "14.09.2025" | "14.09" | "09.2025" | "09"
            if len(parts) == 3:
                # zi_finala, luna, an
                _, month, year = parts
            elif len(parts) == 2:
                # poate fi zi_finala.luna (fără an) SAU luna.an (fără zi_finala)
                p0, p1 = parts
                # dacă ambele sunt numerice și p1 are 4 cifre => luna.an
                if p1.isdigit() and len(p1) == 4:
                    month, year = p0, p1
                else:
                    # interpretăm ca zi_finala.luna (fără an)
                    month, year = p1, str(cur_year)
            elif len(parts) == 1:
                # doar luna (fără an, fără zi_finala)
                month, year = parts[0], str(cur_year)
            else:
                return None

            return f"{int(year):04d}-{int(month):02d}-{int(day_start):02d}"
        else:
            parts = s.split(".")
            if len(parts) == 3:
                day, month, year = parts
            elif len(parts) == 2:
                day, month = parts
                year = str(cur_year)
            else:
                return None
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except Exception:
        return None


@creare_get_concurs_bp.get('/api/concursuri')
def get_concursuri():
    """
    Returnează lista concursurilor:
    [
      { "nume": "...", "perioada": "...", "locatie": "...", "dataStart": "YYYY-MM-DD" },
      ...
    ]
    """
    con = get_conn()
    rows = con.execute("SELECT nume, perioada, locatie FROM concursuri").fetchall()

    data = [{
        "nume": r["nume"],
        "perioada": r["perioada"],
        "locatie": r["locatie"],
        "dataStart": extract_data_start(r["perioada"])
    } for r in rows]

    return jsonify(data)
