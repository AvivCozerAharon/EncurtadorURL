import secrets
import string

_ALPHABET = string.ascii_letters + string.digits


def generate_short_code(length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
