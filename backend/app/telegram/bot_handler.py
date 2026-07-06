"""
TelegramBotHandler — maneja comandos de Telegram y delega mensajes
conversacionales al ConversationOrchestrator existente.

Arquitectura:
- Comandos (/start, /help, /cancel) se manejan localmente
- Mensajes conversacionales se delegan al mismo orquestador que usa la web
- Reutiliza completamente FrontDeskAI, ActionAI, ActionGuard y los Services
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from ..ai.action_ai import ActionAI
from ..ai.front_desk_ai import FrontDeskAI
from ..ai.llm_client import OpenRouterClient
from ..ai.orchestrator import ConversationOrchestrator
from ..database import SessionLocal
from ..exceptions import ClinicFlowError, LLMServiceError

if TYPE_CHECKING:
    from .authenticator import PatientAuthenticator

logger = logging.getLogger(__name__)

_HELP_TEXT = """
🏥 *ClinicFlow - Asistente Virtual*

Puedo ayudarte con:
• 📅 Agendar citas medicas
• ❌ Cancelar citas
• 🔄 Reagendar citas
• 📋 Consultar disponibilidad de medicos
• ⏳ Inscribirte en listas de espera
• 🔗 Aceptar derivaciones

Simplemente escribe lo que necesitas en lenguaje natural.
Ejemplo: "Quiero agendar una cita con medicina general para mañana a las 10am"
"""

_START_UNAUTHENTICATED = """
¡Hola! Soy el asistente virtual de ClinicFlow 🏥

Para comenzar, necesitas vincular tu cuenta de Telegram con tu cuenta de paciente.

*¿Cómo vincular tu cuenta?*
1. Ingresa a la plataforma web de ClinicFlow
2. Ve a tu perfil o configuración
3. Genera un código de vinculación
4. Envíame el comando: `/start CODIGO`

Una vez vinculada tu cuenta, podrás gestionar tus citas directamente desde Telegram.
"""

_UNAUTHENTICATED_MESSAGE = """
⚠️ Tu cuenta de Telegram no está vinculada a ClinicFlow.

Para usar el asistente, primero debes vincular tu cuenta con `/start CODIGO`

Obtén tu código de vinculación desde la plataforma web de ClinicFlow.
"""


class TelegramBotHandler:
    """Maneja la interaccion con usuarios de Telegram, delegando logica conversacional al orquestador."""

    def __init__(self, authenticator: PatientAuthenticator) -> None:
        self._authenticator = authenticator
        # Inicializar componentes de IA (mismo stack que la web)
        llm_client = OpenRouterClient()
        self._orchestrator = ConversationOrchestrator(
            front_desk_ai=FrontDeskAI(llm_client),
            action_ai=ActionAI(llm_client),
        )

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja el comando /start [CODIGO]."""
        if update.effective_user is None or update.message is None:
            return

        telegram_id = str(update.effective_user.id)
        db = SessionLocal()
        try:
            # Verificar si ya esta autenticado
            if self._authenticator.is_linked(db, telegram_id):
                patient_id = self._authenticator.get_patient_id(db, telegram_id)
                logger.info(f"Usuario ya autenticado: telegram_id {telegram_id}, patient_id {patient_id}")
                await update.message.reply_text(
                    "Tu cuenta ya está vinculada ✅\n\n"
                    "Puedes empezar a usar el asistente enviando mensajes directamente.\n"
                    "Usa /help para ver qué puedo hacer por ti."
                )
                return

            # Verificar si se proporciono un codigo
            if not context.args:
                logger.info(f"Comando /start sin codigo: telegram_id {telegram_id}")
                await update.message.reply_text(_START_UNAUTHENTICATED, parse_mode="Markdown")
                return

            # Intentar vincular con el codigo proporcionado
            link_code = context.args[0].upper()
            logger.info(f"Intento de vinculacion: telegram_id {telegram_id}, codigo {link_code}")

            success, message, patient_id = self._authenticator.link_telegram_account(
                db, telegram_id, link_code
            )

            if success:
                logger.info(f"Vinculacion exitosa: telegram_id {telegram_id} -> patient_id {patient_id}")
                await update.message.reply_text(
                    f"{message}\n\n"
                    f"Ahora puedes gestionar tus citas directamente desde Telegram.\n"
                    f"Usa /help para ver todas las opciones disponibles."
                )
            else:
                logger.warning(f"Vinculacion fallida: telegram_id {telegram_id}, razon: {message}")
                await update.message.reply_text(f"❌ {message}")

        finally:
            db.close()

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja el comando /help."""
        if update.effective_user is None or update.message is None:
            return

        telegram_id = str(update.effective_user.id)
        db = SessionLocal()
        try:
            if not self._authenticator.is_linked(db, telegram_id):
                logger.info(f"Comando /help de usuario no autenticado: telegram_id {telegram_id}")
                await update.message.reply_text(
                    "⚠️ Tu cuenta no está vinculada.\n\n"
                    "Para usar el asistente, primero ejecuta `/start CODIGO`\n"
                    "Obtén tu código desde la plataforma web de ClinicFlow.",
                    parse_mode="Markdown",
                )
                return

            logger.info(f"Comando /help: telegram_id {telegram_id}")
            await update.message.reply_text(_HELP_TEXT, parse_mode="Markdown")

        finally:
            db.close()

    async def handle_linkcode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Comando de admin /linkcode <patient_id> — genera un codigo en el proceso del bot."""
        if update.effective_user is None or update.message is None:
            return

        if not context.args:
            await update.message.reply_text(
                "Uso: /linkcode <patient_id>\nEjemplo: /linkcode 1"
            )
            return

        try:
            patient_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("El patient_id debe ser un número entero.")
            return

        db = SessionLocal()
        try:
            from ..exceptions import ClinicFlowError
            code = self._authenticator.generate_link_code(db, patient_id)
            await update.message.reply_text(
                f"✅ Código generado para paciente ID={patient_id}\n\n"
                f"Código: `{code}`\n"
                f"Expira en: 10 minutos\n\n"
                f"Envía al bot: `/start {code}`",
                parse_mode="Markdown",
            )
            logger.info(f"Código generado via /linkcode: patient_id {patient_id}, code {code}")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error: {exc}")
            logger.error(f"Error generando linkcode: {exc}", exc_info=True)
        finally:
            db.close()

    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja el comando /cancel para resetear el estado conversacional."""
        if update.effective_user is None or update.message is None:
            return

        telegram_id = str(update.effective_user.id)
        db = SessionLocal()
        try:
            patient_id = self._authenticator.get_patient_id(db, telegram_id)
            if patient_id is None:
                await update.message.reply_text(_UNAUTHENTICATED_MESSAGE)
                return

            # El reset se hace simplemente informando al usuario
            # La siguiente interaccion creara un nuevo contexto conversacional
            logger.info(f"Comando /cancel: telegram_id {telegram_id}, patient_id {patient_id}")
            await update.message.reply_text(
                "✅ Conversación reiniciada.\n\n"
                "Puedes empezar una nueva solicitud cuando quieras."
            )

        finally:
            db.close()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja mensajes conversacionales, delegando al ConversationOrchestrator."""
        if update.effective_user is None or update.message is None or update.message.text is None:
            return

        telegram_id = str(update.effective_user.id)
        message_text = update.message.text.strip()

        if not message_text:
            return

        db = SessionLocal()
        try:
            # Autenticacion: verificar que el usuario este vinculado
            patient_id = self._authenticator.get_patient_id(db, telegram_id)
            if patient_id is None:
                logger.warning(f"Mensaje de usuario no autenticado: telegram_id {telegram_id}")
                await update.message.reply_text(_UNAUTHENTICATED_MESSAGE)
                return

            logger.info(
                f"Mensaje recibido: telegram_id {telegram_id}, patient_id {patient_id}, "
                f"mensaje: {message_text[:100]}"
            )

            # Delegar al orquestador (mismo flujo que la web, channel="telegram")
            try:
                response = self._orchestrator.handle_message(
                    db=db,
                    patient_id=patient_id,
                    message=message_text,
                    channel="telegram",
                )

                reply_text = response.reply

                # Telegram tiene un limite de 4096 caracteres por mensaje
                # Si la respuesta es mas larga, dividirla en chunks
                if len(reply_text) > 4096:
                    chunks = self._split_message(reply_text, 4096)
                    for chunk in chunks:
                        await update.message.reply_text(chunk)
                else:
                    await update.message.reply_text(reply_text)

                logger.info(
                    f"Respuesta enviada: telegram_id {telegram_id}, intent {response.intent}, "
                    f"action_taken: {response.action_taken[:100] if response.action_taken else 'None'}"
                )

            except LLMServiceError as exc:
                # Error del cliente de OpenRouter (timeout, rate limit, etc.)
                logger.error(f"LLMServiceError al procesar mensaje: {exc}", exc_info=True)
                await update.message.reply_text(
                    "⚠️ El servicio de IA no está disponible temporalmente.\n"
                    "Por favor intenta de nuevo en unos momentos."
                )

            except ClinicFlowError as exc:
                # Error de reglas de negocio (el orquestador ya manejo estos,
                # pero si escapan hasta aqui, informar al usuario)
                logger.error(f"ClinicFlowError al procesar mensaje: {exc}", exc_info=True)
                await update.message.reply_text(f"❌ {exc.message}")

            except Exception as exc:
                # Error inesperado: logear con stack trace completo y dar mensaje generico
                logger.error(
                    f"Error inesperado al procesar mensaje de telegram_id {telegram_id}: {exc}",
                    exc_info=True,
                )
                await update.message.reply_text(
                    "❌ Se produjo un error inesperado. Por favor intenta de nuevo.\n"
                    "Si el problema persiste, contacta al administrador."
                )

        finally:
            db.close()

    def _split_message(self, text: str, max_length: int = 4096) -> list[str]:
        """Divide un mensaje largo en chunks que respeten el limite de Telegram."""
        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            # Intentar cortar en un salto de linea cercano al limite
            split_index = text.rfind("\n", 0, max_length)
            if split_index == -1:
                # No hay saltos de linea, cortar en el limite
                split_index = max_length

            chunks.append(text[:split_index])
            text = text[split_index:].lstrip()

        return chunks
