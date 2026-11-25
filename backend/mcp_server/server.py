from typing import Optional
from mcp.server.mcpserver import Context, MCPServer

from backend.config import get_conn
from backend.mcp_server.auth import get_authenticated_user, require_roles

mcp = MCPServer("Hwarang_Academy_MCP")


# ---------------------------------------------------------------------------
# 1. UNELTE PUBLICE (nu necesită autentificare)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_club_calendar(tip_eveniment: Optional[str] = None, limit: int = 20) -> list[dict]:
    """
    Returnează evenimentele active din calendarul Hwarang Academy (antrenamente speciale,
    concursuri, examene, stagii). Opțional filtrează după tip_eveniment.
    """
    sql = """
        SELECT id, titlu, data_start, data_sfarsit, locatie, descriere, tip_eveniment
        FROM calendar_club
        WHERE activ = TRUE
    """
    params = []

    if tip_eveniment:
        sql += " AND LOWER(tip_eveniment) = LOWER(?)"
        params.append(tip_eveniment.strip())

    sql += " ORDER BY data_start ASC LIMIT ?"
    params.append(min(max(limit, 1), 50))

    with get_conn() as con:
        rows = con.execute(sql, tuple(params)).fetchall()

    return [
        {
            "id": r["id"],
            "titlu": r["titlu"],
            "data_start": str(r["data_start"]) if r["data_start"] else None,
            "data_sfarsit": str(r["data_sfarsit"]) if r["data_sfarsit"] else None,
            "locatie": r["locatie"],
            "descriere": r["descriere"],
            "tip_eveniment": r["tip_eveniment"],
        }
        for r in rows
    ]


@mcp.tool()
def list_open_competitions() -> list[dict]:
    """
    Returnează lista concursurilor de Taekwon-Do cu înscrierile deschise în prezent.
    """
    sql = """
        SELECT id, nume, perioada, locatie, cere_inaltime
        FROM concursuri
        WHERE inscrieri_deschise = TRUE
        ORDER BY id DESC
    """
    with get_conn() as con:
        rows = con.execute(sql).fetchall()

    return [
        {
            "id": r["id"],
            "nume": r["nume"],
            "perioada": r["perioada"],
            "locatie": r["locatie"],
            "cere_inaltime": bool(r["cere_inaltime"]),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 2. UNELTE PROTEJATE PRIN RBAC (necesită JWT în header-ul Authorization)
# ---------------------------------------------------------------------------

@mcp.tool()
def get_my_children(ctx: Context) -> dict:
    """
    Returnează lista copiilor asociați părintelui autentificat curent și grupa fiecăruia.
    Necesită autentificare (rol: parinte sau admin).
    """
    user = get_authenticated_user(ctx)
    require_roles(user, {"parinte", "admin"})

    sql = """
        SELECT id, nume, data_nasterii, gen, grupa_text
        FROM copii
        WHERE id_parinte = ?
        ORDER BY nume ASC
    """
    with get_conn() as con:
        rows = con.execute(sql, (user.user_id,)).fetchall()

    return {
        "parinte": user.username,
        "copii": [
            {
                "id": r["id"],
                "nume": r["nume"],
                "data_nasterii": str(r["data_nasterii"]) if r["data_nasterii"] else None,
                "gen": r["gen"],
                "grupa": r["grupa_text"],
            }
            for r in rows
        ],
    }


if __name__ == "__main__":
    # Pornește serverul MCP pe http://127.0.0.1:8000/mcp
    mcp.run(transport="streamable-http")