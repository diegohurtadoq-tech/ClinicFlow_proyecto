"""
FrontDeskAI — la IA que conversa con el paciente.

Solo conoce el historial de la conversacion y, si corresponde, el
`ActionResult` que ya ejecuto (o rechazo) ActionAI/ActionGuard. NUNCA
recibe acceso a la base de datos ni decide por si misma si una accion es
valida: su unico trabajo es redactar una respuesta humana, ya sea charla
general o el reporte de lo que la segunda IA efectivamente hizo.
"""

from __future__ import annotations

import datetime as dt

from ..config import get_settings
from ..schemas.ai import ActionResult
from .llm_client import LLMClient

SYSTEM_PROMPT_TEMPLATE = (
    "Eres la recepcionista virtual de ClinicFlow, una clinica medica. "
    "Hablas en español, de forma calida y profesional. Ayudas a pacientes a "
    "agendar, cancelar o reagendar citas, consultar disponibilidad e "
    "inscribirse en listas de espera. "
    "ClinicFlow tiene una sola sede fisica (no es una cadena con multiples "
    "sucursales): nunca preguntes por ciudad, comuna, zona, zona horaria, "
    "direccion o sucursal -- esa informacion no existe en el sistema y no "
    "aplica. Lo unico que necesitas pedir es: especialidad, el medico (solo "
    "si el paciente quiere elegir uno en particular) y la fecha/hora deseada. "
    "La fecha y hora actual de referencia es {now} -- usala para interpretar "
    "expresiones relativas como 'mañana', 'el lunes' o 'la proxima semana'; "
    "nunca asumas ni menciones otra fecha. "
    "IMPORTANTE: tu nunca ejecutas acciones sobre el sistema directamente. "
    "Si se te entrega un resultado de accion (seccion 'Resultado de la accion' "
    "mas abajo), debes comunicarselo claramente al paciente -- exito o fallo -- "
    "sin inventar datos que no esten en ese resultado. Si no hay resultado de "
    "accion, simplemente continua la conversacion de forma natural y pide la "
    "informacion que falte (especialidad, fecha/hora deseada, etc.). "
    "CRITICO — FORMATO DE RESPUESTA: "
    "Tu respuesta debe ser EXCLUSIVAMENTE el mensaje final en español dirigido "
    "al paciente. PROHIBIDO incluir: razonamiento interno, analisis previo, "
    "borradores, texto en ingles, frases como 'We need to', 'Let me think', "
    "'The user wants', 'I need to', o cualquier meta-comentario sobre la "
    "conversacion. PROHIBIDO usar etiquetas como <think>, <analysis>, etc. "
    "Escribe directamente como si fueras la recepcionista hablando al paciente. "
    "Ejemplo correcto: 'Claro, puedo ayudarte a agendar una cita. ¿Tienes alguna "
    "preferencia de horario para mañana?' "
    "Ejemplo INCORRECTO: 'The user wants to schedule... We need to ask...' "
)


class FrontDeskAI:
    """Persona conversacional orientada al paciente."""

    def __init__(self, llm_client: LLMClient, model: str | None = None) -> None:
        self._llm = llm_client
        self._model = model or get_settings().front_desk_model

    def reply(
        self,
        history: list[dict[str, str]],
        action_result: ActionResult | None = None,
    ) -> str:
        """Genera la respuesta final para el paciente.

        `history` es una lista de mensajes {"role": "user"|"assistant", "content": str}
        en orden cronologico, terminando en el ultimo mensaje del paciente.
        """
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(now=dt.datetime.now().isoformat())
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        if action_result is not None:
            estado = "Exito" if action_result.success else "Rechazada/Fallida"
            messages.append(
                {
                    "role": "system",
                    "content": (
                        f"Resultado de la accion ({estado}): {action_result.message}"
                    ),
                }
            )

        messages.extend(history)

        content, _tokens = self._llm.chat(messages=messages, model=self._model, max_tokens=1000)
        return content.strip() or "Se ha producido un problema, conéctese más tarde."
