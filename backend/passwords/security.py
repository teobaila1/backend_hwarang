from werkzeug.security import generate_password_hash, check_password_hash


def hash_password(plain_password: str) -> str:
    """
    Generează un hash securizat (pbkdf2:sha256 implicit în versiunile noi de Werkzeug).
    """
    if not plain_password:
        return ""
    return generate_password_hash(plain_password)


def check_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifică dacă parola introdusă corespunde cu hash-ul din DB.
    Știe să interpreteze automat formatele: pbkdf2:sha256, scrypt, sha256 etc.
    """
    if not hashed_password or not plain_password:
        return False

    try:
        # ATENȚIE: Werkzeug cere ordinea (HASH, PAROLĂ_CLARĂ)
        return check_password_hash(hashed_password, plain_password)
    except Exception as e:
        print(f"[SECURITY ERROR] Format hash nerecunoscut sau eroare internă: {e}")
        return False