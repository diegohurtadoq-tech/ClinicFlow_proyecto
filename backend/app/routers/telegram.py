"""
Router de Telegram: endpoints para generar codigos de vinculacion y recibir webhooks.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from ..auth.dependencies import get_current_user, require_role
from ..database import get_db
from ..exceptions import ClinicFlowError
from ..models.user import Patient, User
from ..telegram.authenticator import PatientAuthenticator
from ..telegram.bot_handler import TelegramBotHandler

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

logger = logging.getLogger(__name__)
_authenticator = PatientAuthenticator()
_telegram_application: Application | None = None


class LinkCodeResponse(BaseModel):
    """Respuesta con codigo de vinculacion."""

    code: str
    expires_in_minutes: int
    instructions: str


async def _get_telegram_application() -> Application:
    global _telegram_application
    if _telegram_application is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN no configurado")

        application = Application.builder().token(token).build()
        bot_handler = TelegramBotHandler(_authenticator)

        application.add_handler(CommandHandler("start", bot_handler.handle_start))
        application.add_handler(CommandHandler("help", bot_handler.handle_help))
        application.add_handler(CommandHandler("cancel", bot_handler.handle_cancel))
        application.add_handler(CommandHandler("linkcode", bot_handler.handle_linkcode))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message)
        )
        await application.initialize()
        _telegram_application = application

    return _telegram_application


@router.post("/link-code", response_model=LinkCodeResponse)
def generate_link_code(
    current_user: User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
) -> LinkCodeResponse:
    """Genera un codigo de vinculacion para el paciente autenticado.

    El codigo expira en 10 minutos y puede ser usado una sola vez para
    vincular la cuenta del paciente con Telegram.
    """
    try:
        code = _authenticator.generate_link_code(db, current_user.id)

        return LinkCodeResponse(
            code=code,
            expires_in_minutes=10,
            instructions=(
                f"Envia este codigo al bot de Telegram:\n"
                f"/start {code}\n\n"
                f"El codigo expira en 10 minutos."
            ),
        )

    except ClinicFlowError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


@router.delete("/link")
def unlink_telegram_account(
    current_user: User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Desvincula la cuenta de Telegram del paciente autenticado."""
    patient = db.get(Patient, current_user.id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    patient.telegram_id = None
    db.commit()

    return {"message": "Cuenta de Telegram desvinculada correctamente."}


@router.post("/webhook")
async def telegram_webhook(update_payload: dict[str, Any]) -> dict[str, Any]:
    """Recibe updates de Telegram y los procesa sin usar polling."""
    try:
        application = await _get_telegram_application()
        update = Update.de_json(update_payload, application.bot)
        if update is None:
            return {"ok": True}

        await application.process_update(update)
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error procesando webhook de Telegram: %s", exc)
        return {"ok": False, "error": str(exc)}
