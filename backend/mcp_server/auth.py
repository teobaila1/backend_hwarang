from dataclasses import dataclass
from typing import Optional
import jwt

from backend.config import SECRET_KEY, get_conn


@dataclass
class AuthUser:
    user_id: int
    username: str
    rol: str
    toate_rolurile: list[str]


def _extract_token_from_ctx(ctx) -> Optional[str]:
    """Extrage JWT-ul din header-ele HTTP ale cererii MCP."""
    if not ctx or not getattr(ctx, "request_context", None):
        return None

    request = getattr(ctx.request_context, "request", None)
    if request is None or not hasattr(request, "headers"):
        return None

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()

    return request.headers.get("x-access-token")


def get_authenticated_user(ctx) -> AuthUser:
    """
    Validează JWT-ul din request și încarcă toate rolurile utilizatorului
    din tabela `roluri` (plus rolul principal din token).
    """
    token = _extract_token_from_ctx(ctx)
    if not token:
        raise PermissionError("Autentificare necesară: lipsește header-ul Authorization: Bearer <token>.")

    try:
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"], options={"leeway": 60})
    except jwt.ExpiredSignatureError:
        raise PermissionError("Sesiunea a expirat. Te rugăm să te reloghezi.")
    except jwt.InvalidTokenError:
        raise PermissionError("Token JWT invalid.")

    user_id = data["user_id"]
    primary_role = (data.get("rol") or "elev").lower()
    username = data.get("username", "")

    # Citim și rolurile suplimentare din tabela `roluri` (RBAC complet)
    roles = {primary_role}
    with get_conn() as con:
        cur = con.execute("SELECT rol FROM roluri WHERE id_user = ?", (user_id,))
        for row in cur.fetchall():
            if row["rol"]:
                roles.add(row["rol"].lower())

    return AuthUser(
        user_id=user_id,
        username=username,
        rol=primary_role,
        toate_rolurile=sorted(roles),
    )


def require_roles(user: AuthUser, allowed_roles: set[str]) -> None:
    """Verifică dacă utilizatorul are cel puțin unul dintre rolurile permise."""
    if not any(r in allowed_roles for r in user.toate_rolurile):
        raise PermissionError(
            f"Acces interzis pentru rolurile {user.toate_rolurile}. "
            f"Roluri necesare: {sorted(allowed_roles)}."
        )