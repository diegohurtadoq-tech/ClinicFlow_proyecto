"""
Configuracion de la aplicacion, leida desde variables de entorno (.env).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Valores de configuracion centralizados."""

    database_url: str
    openrouter_api_key: str
    front_desk_model: str
    action_model: str
    jwt_secret: str


def _default_database_url() -> str:
    """SQLite local en desarrollo; en Vercel el filesystem del proyecto es de
    solo lectura, asi que sin DATABASE_URL explicito usamos /tmp (escribible
    pero efimero entre invocaciones serverless)."""
    if os.getenv("VERCEL"):
        return "sqlite:////tmp/clinicflow.db"
    return "sqlite:///./clinicflow.db"


@lru_cache
def get_settings() -> Settings:
    """Retorna (y cachea) la configuracion leida del entorno."""
    return Settings(
        database_url=os.getenv("DATABASE_URL", _default_database_url()),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        front_desk_model=os.getenv("FRONT_DESK_MODEL", "openrouter/free"),
        action_model=os.getenv("ACTION_MODEL", "openrouter/free"),
        # Valor de desarrollo por defecto; SIEMPRE sobreescribir en produccion via .env.
        jwt_secret=os.getenv("JWT_SECRET", "clinicflow-dev-secret-do-not-use-in-production"),
    )
