"""
ActionAI — la segunda IA. Lee la conversacion y produce una unica salida
estructurada (`ProposedAction`), validada con Pydantic. No tiene acceso a
la base de datos: solo "rellena un formulario tipado". Quien ejecuta la
accion (tras pasar por ActionGuard) es el `ConversationOrchestrator`,
llamando a los Services de dominio.

Cualquier salida que no se pueda parsear o validar degrada a
`Intent.NONE` (fail closed) -- nunca se adivina una accion.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re

from pydantic import ValidationError

from ..config import get_settings
from ..schemas.ai import Intent, ProposedAction
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = (
    "Eres un extractor de intenciones para ClinicFlow. Lee la conversacion "
    "entre la recepcionista virtual y el paciente (patient_id={patient_id}) y "
    "responde EXCLUSIVAMENTE con un objeto JSON, sin texto adicional, sin "
    "markdown, sin razonamiento, sin etiquetas <think>, que cumpla este "
    "esquema:\n"
    "{{\n"
    '  "intent": uno de [CREATE_APPOINTMENT, CANCEL_APPOINTMENT, '
    "RESCHEDULE_APPOINTMENT, CHECK_AVAILABILITY, JOIN_WAITLIST, "
    "ACCEPT_REFERRAL, NONE],\n"
    '  "patient_id": siempre {patient_id} (nunca otro valor),\n'
    '  "specialty": string o null,\n'
    '  "doctor_id": entero o null,\n'
    '  "appointment_id": entero o null (la cita a cancelar/reagendar, si el '
    "paciente la menciono),\n"
    '  "referral_id": entero o null,\n'
    '  "requested_datetime": fecha/hora ISO 8601 o null,\n'
    '  "notes": string corto o null\n'
    "}}\n"
    "Usa NONE si el paciente solo esta charlando, preguntando algo general, o "
    "si falta informacion clave para ejecutar la accion. "
    "Para CHECK_AVAILABILITY y CREATE_APPOINTMENT NO necesitas un doctor_id si "
    "el paciente solo menciono una especialidad (p.ej. 'medicina general') sin "
    "pedir un medico en particular: deja doctor_id en null y completa "
    "'specialty' en su lugar, el sistema buscara los medicos de esa "
    "especialidad por su cuenta. Solo pon doctor_id cuando el paciente nombro "
    "un medico especifico de la lista de abajo, o uno que ya aparecio antes "
    "en la conversacion (p.ej. en un resultado de disponibilidad previo). "
    f"La fecha y hora actual de referencia es {{now}}.\n\n"
    "Medicos de la clinica (nombre y especialidad -> id a usar si el paciente "
    "nombra a ese medico):\n{doctors_roster}"
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        raise ValueError("No se encontro un bloque JSON en la respuesta del modelo.")
    return json.loads(match.group(0))


def _format_doctors_roster(doctors: list[dict] | None) -> str:
    if not doctors:
        return "(no hay medicos registrados)"
    return "\n".join(f"- id={d['id']}: {d['name']} ({d['specialty']})" for d in doctors)


class ActionAI:
    """Extrae una ProposedAction estructurada desde el historial de conversacion."""

    _MAX_ATTEMPTS = 2

    def __init__(self, llm_client: LLMClient, model: str | None = None) -> None:
        self._llm = llm_client
        self._model = model or get_settings().action_model

    def extract(
        self,
        history: list[dict[str, str]],
        patient_id: int,
        doctors: list[dict] | None = None,
    ) -> ProposedAction:
        """`doctors` es una lista plana de {id, name, specialty} que el
        orquestador lee de la base de datos -- ActionAI sigue sin tocar la
        base de datos directamente, solo recibe este listado como texto de
        referencia (igual que un recepcionista humano conoce a sus colegas).

        Algunos modelos gratuitos "piensan" antes de responder y esos tokens
        de razonamiento consumen el presupuesto de `max_tokens` aunque se
        excluyan del texto visible, truncando el JSON final a mitad de
        camino. Un reintento unico (igual que el de OpenRouterClient para
        contenido vacio) resuelve la mayoria de esos casos sin tener que
        degradar a NONE por una mala racha puntual del modelo."""
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            patient_id=patient_id,
            now=dt.datetime.now().isoformat(),
            doctors_roster=_format_doctors_roster(doctors),
        )
        messages = [{"role": "system", "content": system_prompt}, *history]

        last_exc: Exception | None = None
        last_content = ""
        for _attempt in range(self._MAX_ATTEMPTS):
            content, _tokens = self._llm.chat(
                messages=messages,
                model=self._model,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )
            last_content = content
            try:
                payload = _extract_json(content)
                return ProposedAction.model_validate(payload)
            except (ValueError, json.JSONDecodeError, ValidationError) as exc:
                last_exc = exc

        logger.warning(
            "ActionAI: no se pudo extraer una accion valida tras %d intento(s) (%s). Salida cruda: %r",
            self._MAX_ATTEMPTS,
            last_exc,
            last_content[:500],
        )
        return ProposedAction(intent=Intent.NONE, patient_id=patient_id)
