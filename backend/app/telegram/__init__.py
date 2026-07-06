"""
Modulo de integracion con Telegram.
"""

from .authenticator import PatientAuthenticator

# TelegramBotHandler requiere python-telegram-bot instalado
# Solo importar si se va a usar (evita romper tests sin la libreria)
try:
    from .bot_handler import TelegramBotHandler

    __all__ = ["PatientAuthenticator", "TelegramBotHandler"]
except ImportError:
    __all__ = ["PatientAuthenticator"]
