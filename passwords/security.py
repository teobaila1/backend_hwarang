# security.py
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(plain: str) -> str:
    # același algoritm peste tot (register + reset)
    return generate_password_hash(plain, method="pbkdf2:sha256", salt_length=16)

def check_password(stored_hash: str, plain: str) -> bool:
    return check_password_hash(stored_hash, plain)
