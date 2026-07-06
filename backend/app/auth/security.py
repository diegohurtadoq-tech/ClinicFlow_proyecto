"""
Hashing de contraseñas. Implementacion solo con la libreria estandar
(hashlib.pbkdf2_hmac) para no depender de una extension C que pueda no
tener wheel disponible en todas las plataformas (ver psycopg2-binary).

Formato de almacenamiento: "<salt_hex>$<hash_hex>".
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    """Genera un hash con salt aleatorio, listo para guardar en `User.password_hash`."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verifica `password` contra un hash generado por `hash_password`."""
    try:
        salt, digest_hex = stored.split("$", 1)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), digest_hex)
