"""
Dependencies de FastAPI para autenticacion/autorizacion.

`get_current_user` es el unico lugar que confia en el contenido del token
(ya verificado); todo lo demas (routers, services) recibe un `User` real ya
resuelto, nunca un id "de confianza" enviado por el cliente. Esto es lo que
cierra el hueco que tenia antes el endpoint de conversacion, donde
`patient_id` venia de la URL sin ninguna verificacion.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..database import get_db
from ..exceptions import AuthenticationError, SecurityViolationError
from ..models.user import User
from .jwt_handler import decode_access_token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthenticationError("Falta el token de autenticacion.")

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise AuthenticationError("Token invalido o expirado.")

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise AuthenticationError("El usuario del token ya no existe.")
    return user


def require_role(*roles: str):
    """Dependency factory: exige que el usuario autenticado tenga uno de `roles`."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise SecurityViolationError(
                f"Se requiere rol {roles}, pero el usuario tiene rol '{current_user.role}'."
            )
        return current_user

    return checker
