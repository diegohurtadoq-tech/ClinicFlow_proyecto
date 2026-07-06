"""
Modelo de codigos de vinculacion Telegram-Paciente.

Persiste los codigos en la base de datos para que el servidor Uvicorn
(que genera el codigo via la web) y el proceso del bot de Telegram
(que lo valida) compartan el mismo almacenamiento, sin depender de memoria
de proceso.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TelegramLinkCode(Base):
    """Codigo de un solo uso para vincular una cuenta de Telegram con un Paciente."""

    __tablename__ = "telegram_link_codes"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime())
    used: Mapped[bool] = mapped_column(default=False, server_default="0")
