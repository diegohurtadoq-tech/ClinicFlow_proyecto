"""
ActionGuard — la verificacion de seguridad/negocio que corre ENTRE las dos
IAs y los Services. Es codigo Python deterministico, no un modelo de
lenguaje: el cumplimiento de reglas de negocio no puede depender de que un
LLM "decida" comportarse bien (asi lo exige el enunciado del curso).

Verifica:
  1. Que la accion no intente operar sobre un paciente distinto al dueño
     de la conversacion (suplantacion via prompt injection).
  2. Que el intent este dentro de la lista permitida (ya lo fuerza Pydantic,
     se re-valida aqui por defensa en profundidad).
  3. Que los campos de texto libre no contengan patrones de inyeccion
     (SQL, intentos de "jailbreak" del prompt). Esto es defensa en
     profundidad: igualmente ninguna IA construye SQL nunca -- todo acceso
     a datos pasa por el ORM de SQLAlchemy con consultas parametrizadas.

Si la validacion falla, lanza `SecurityViolationError` y la accion nunca
llega a los Services de dominio.
"""

from __future__ import annotations

import re

from ..exceptions import SecurityViolationError
from ..schemas.ai import Intent, ProposedAction

_SUSPICIOUS_PATTERNS = [
    re.compile(r"ignor[ae].{0,30}instruccion", re.IGNORECASE),
    re.compile(r"ignore.{0,30}(previous|prior|system)?\s*instructions", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"delete\s+from", re.IGNORECASE),
    re.compile(r"union\s+select", re.IGNORECASE),
    re.compile(r";\s*--"),
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"actua\s+como\s+(el\s+)?(admin|administrador|sistema)", re.IGNORECASE),
]


class ActionGuard:
    """Verificacion deterministica de seguridad/negocio sobre una ProposedAction."""

    def validate(self, action: ProposedAction, conversation_patient_id: int) -> None:
        """Lanza SecurityViolationError si la accion no debe ejecutarse."""
        if action.intent == Intent.NONE:
            return

        if action.intent not in set(Intent):
            raise SecurityViolationError(f"Intencion no reconocida: {action.intent!r}.")

        if action.patient_id is None or action.patient_id != conversation_patient_id:
            raise SecurityViolationError(
                "La accion propuesta intenta operar sobre un paciente distinto "
                "al dueño de esta conversacion."
            )

        for field_text in action.free_text_fields():
            self._check_injection(field_text)

    def _check_injection(self, text: str) -> None:
        for pattern in _SUSPICIOUS_PATTERNS:
            if pattern.search(text):
                raise SecurityViolationError(
                    f"Texto rechazado por contener un patron sospechoso: '{text[:60]}'."
                )
