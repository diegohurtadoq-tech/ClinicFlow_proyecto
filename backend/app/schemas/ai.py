"""
Contrato estructurado entre las dos IAs.

`ActionAI` debe producir SIEMPRE un `ProposedAction` valido (o degradar a
`Intent.NONE` si no puede). Este esquema es deliberadamente estrecho: solo
contiene los campos que un ActionGuard/Service puede verificar de forma
determinista. La IA nunca emite SQL ni texto libre que se ejecute; solo
puede "elegir" entre estos campos tipados.
"""

from __future__ import annotations

import datetime as dt
import enum

from pydantic import BaseModel, Field


class Intent(str, enum.Enum):
    CREATE_APPOINTMENT = "CREATE_APPOINTMENT"
    CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
    RESCHEDULE_APPOINTMENT = "RESCHEDULE_APPOINTMENT"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    JOIN_WAITLIST = "JOIN_WAITLIST"
    ACCEPT_REFERRAL = "ACCEPT_REFERRAL"
    NONE = "NONE"


class ProposedAction(BaseModel):
    """Salida estructurada de ActionAI tras leer la conversacion."""

    intent: Intent = Intent.NONE
    patient_id: int | None = None
    specialty: str | None = Field(default=None, max_length=80)
    doctor_id: int | None = None
    appointment_id: int | None = None
    referral_id: int | None = None
    requested_datetime: dt.datetime | None = None
    notes: str | None = Field(default=None, max_length=300)

    def free_text_fields(self) -> list[str]:
        """Campos de texto libre que el ActionGuard debe inspeccionar por patrones sospechosos."""
        return [f for f in (self.specialty, self.notes) if f]


class ActionResult(BaseModel):
    """Resultado de ejecutar (o rechazar) una ProposedAction."""

    success: bool
    message: str
    data: dict | None = None
