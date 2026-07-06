"""
Script principal del bot de Telegram para ClinicFlow.

Ejecutar con: python telegram_bot.py

Requiere:
- TELEGRAM_BOT_TOKEN en variables de entorno
- DATABASE_URL, OPENROUTER_API_KEY (heredados de la configuracion existente)
"""

import asyncio
import logging
import os
import signal
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Agregar el directorio backend al path para imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.database import Base, engine
from app.telegram.authenticator import PatientAuthenticator
from app.telegram.bot_handler import TelegramBotHandler

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def get_telegram_token() -> str:
    """Obtiene el token del bot de Telegram desde variables de entorno."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN no encontrado en variables de entorno.\n"
            "Por favor configura esta variable antes de ejecutar el bot.\n"
            "Ejemplo: export TELEGRAM_BOT_TOKEN='tu_token_aqui'"
        )
    return token.strip()


async def shutdown(application: Application) -> None:
    """Maneja el cierre graceful del bot."""
    logger.info("Iniciando shutdown del bot...")
    await application.stop()
    await application.shutdown()
    logger.info("Bot detenido exitosamente")


def setup_signal_handlers(application: Application) -> None:
    """Configura handlers para señales de sistema (SIGINT, SIGTERM)."""

    def signal_handler(signum: int, frame) -> None:
        logger.info(f"Señal {signum} recibida, deteniendo bot...")
        asyncio.create_task(shutdown(application))

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main() -> None:
    """Punto de entrada principal del bot."""
    try:
        # Verificar token antes de continuar
        token = get_telegram_token()
        logger.info("Token de Telegram cargado exitosamente")

        # Crear tablas si no existen (incluye telegram_link_codes)
        logger.info("Verificando esquema de base de datos...")
        from app import models as _models  # noqa: F401 — registra todos los modelos
        Base.metadata.create_all(bind=engine)
        logger.info("Base de datos inicializada")

        # Inicializar componentes
        authenticator = PatientAuthenticator()
        bot_handler = TelegramBotHandler(authenticator)
        logger.info("Componentes de autenticacion y handler inicializados")

        # Crear aplicacion de Telegram
        application = Application.builder().token(token).build()

        # Registrar handlers de comandos
        application.add_handler(CommandHandler("start", bot_handler.handle_start))
        application.add_handler(CommandHandler("help", bot_handler.handle_help))
        application.add_handler(CommandHandler("cancel", bot_handler.handle_cancel))
        application.add_handler(CommandHandler("linkcode", bot_handler.handle_linkcode))

        # Registrar handler de mensajes (cualquier texto que no sea comando)
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message)
        )

        logger.info("Handlers registrados exitosamente")

        # Configurar signal handlers para shutdown graceful
        setup_signal_handlers(application)

        # Iniciar bot con polling
        logger.info("=" * 60)
        logger.info("🤖 ClinicFlow Telegram Bot iniciado exitosamente")
        logger.info("Presiona Ctrl+C para detener el bot")
        logger.info("=" * 60)

        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except ValueError as exc:
        logger.error(f"Error de configuracion: {exc}")
        sys.exit(1)
    except Exception as exc:
        logger.error(f"Error fatal al iniciar el bot: {exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
