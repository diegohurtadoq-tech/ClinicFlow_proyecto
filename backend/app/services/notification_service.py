"""Servicio de notificaciones con soporte basico para Telegram."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

try:
    from telegram import Bot
except ImportError:  # pragma: no cover - depende del entorno de despliegue
    Bot = None  # type: ignore[assignment,misc]


class NotificationService:
    """Envia notificaciones a pacientes. Implementacion actual: log + Telegram opcional."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self._bot: Any | None = None

    def _get_bot(self) -> Any | None:
        if self._bot is not None:
            return self._bot
        if Bot is None:
            return None

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            return None

        self._bot = Bot(token=token)
        return self._bot

    def _send_via_telegram(self, chat_id: str, message: str) -> None:
        bot = self._get_bot()
        if bot is None:
            return

        async def _send() -> None:
            await bot.send_message(chat_id=chat_id, text=message)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_send())
        else:
            loop.create_task(_send())

    def notify(self, patient_id: int, message: str, db: Session | None = None) -> None:
        """Notifica a un paciente. Si existe un telegram_id y el bot esta configurado, lo intenta por Telegram."""
        self.sent.append((patient_id, message))
        print(f"[notificacion] paciente={patient_id}: {message}")

        if db is None:
            return

        from ..models.user import Patient

        patient = db.get(Patient, patient_id)
        if patient is None or not getattr(patient, "telegram_id", None):
            return

        try:
            self._send_via_telegram(str(patient.telegram_id), message)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("No se pudo enviar mensaje por Telegram al paciente %s: %s", patient_id, exc)
