"""
Cita medica: nucleo del dominio. Modelada como una maquina de estados de
6 estados discretos, con una tabla explicita de transiciones validas.
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..exceptions import InvalidStateTransitionError


class AppointmentStatus(str, enum.Enum):
    """Los 6 estados posibles de una Cita."""

    PENDIENTE = "pendiente"
    CONFIRMADA = "confirmada"
    CANCELADA = "cancelada"
    REAGENDADA = "reagendada"
    COMPLETADA = "completada"
    NO_ASISTIO = "no_asistio"


# Estados terminales: no admiten ninguna transicion de salida.
_TERMINAL_STATES = {
    AppointmentStatus.CANCELADA,
    AppointmentStatus.REAGENDADA,
    AppointmentStatus.COMPLETADA,
    AppointmentStatus.NO_ASISTIO,
}

# Tabla de transiciones validas (estado actual -> estados permitidos).
ALLOWED_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.PENDIENTE: {
        AppointmentStatus.CONFIRMADA,
        AppointmentStatus.CANCELADA,
        AppointmentStatus.REAGENDADA,
    },
    AppointmentStatus.CONFIRMADA: {
        AppointmentStatus.CANCELADA,
        AppointmentStatus.REAGENDADA,
        AppointmentStatus.COMPLETADA,
        AppointmentStatus.NO_ASISTIO,
    },
}


class Appointment(Base):
    """Una cita medica entre un Paciente y un Doctor."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    datetime_: Mapped[dt.datetime] = mapped_column("datetime", DateTime())
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.PENDIENTE
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    referral_id: Mapped[int | None] = mapped_column(ForeignKey("referrals.id"), nullable=True)
    rescheduled_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(), server_default=func.now())
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(), nullable=True)

    patient: Mapped["Patient"] = relationship(  # noqa: F821
        back_populates="appointments", foreign_keys=[patient_id]
    )

    def can_transition_to(self, new_status: AppointmentStatus) -> bool:
        """Indica si la transicion `self.status -> new_status` es valida."""
        return new_status in ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, new_status: AppointmentStatus) -> None:
        """Aplica la transicion de estado, validando contra la tabla de transiciones."""
        if self.status in _TERMINAL_STATES:
            raise InvalidStateTransitionError(
                f"La cita {self.id} esta en estado terminal '{self.status.value}' "
                f"y no admite mas transiciones."
            )
        if not self.can_transition_to(new_status):
            raise InvalidStateTransitionError(
                f"Transicion invalida: '{self.status.value}' -> '{new_status.value}'."
            )
        self.status = new_status

    def is_active(self) -> bool:
        """Una cita 'activa' ocupa un cupo de agenda (no esta cancelada/reagendada/etc.)."""
        return self.status in {AppointmentStatus.PENDIENTE, AppointmentStatus.CONFIRMADA}

    def __repr__(self) -> str:
        return (
            f"Appointment(id={self.id}, patient_id={self.patient_id}, "
            f"doctor_id={self.doctor_id}, status={self.status.value})"
        )
