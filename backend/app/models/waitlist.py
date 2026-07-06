"""
Lista de espera: pacientes en espera de un cupo, con priorizacion basica.
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class WaitlistPriority(str, enum.Enum):
    NORMAL = "normal"
    ALTA = "alta"


class WaitlistEntry(Base):
    """Una inscripcion de un Paciente en la lista de espera de una especialidad."""

    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    specialty: Mapped[str] = mapped_column(String(80))
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    priority: Mapped[WaitlistPriority] = mapped_column(
        Enum(WaitlistPriority), default=WaitlistPriority.NORMAL
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(), server_default=func.now())

    def sort_key(self) -> tuple[int, dt.datetime]:
        """Orden de prioridad: alta antes que normal; dentro de cada nivel, el mas antiguo primero."""
        priority_rank = 0 if self.priority == WaitlistPriority.ALTA else 1
        return (priority_rank, self.created_at)
