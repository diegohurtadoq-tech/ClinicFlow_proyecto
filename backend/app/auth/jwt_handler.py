"""
Emision y verificacion de tokens JWT (componente "Auth (JWT)" de la
arquitectura). El token lleva el id de usuario (`sub`) y su rol (`role`),
que es lo unico que necesitan los dependencies de FastAPI para autorizar.
"""

from __future__ import annotations

import datetime as dt

import jwt

from ..config import get_settings

ALGORITHM = "HS256"
EXPIRES_MINUTES = 60 * 24  # 24 horas


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=EXPIRES_MINUTES),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Lanza jwt.PyJWTError (token invalido/expirado) si la verificacion falla."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
