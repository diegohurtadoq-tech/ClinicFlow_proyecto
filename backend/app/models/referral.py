"""
Derivacion: un Doctor deriva a un Paciente hacia otra especialidad
(por ejemplo, para realizar un examen). El paciente puede luego aceptar
la derivacion, lo que funciona de forma similar a tomar una hora.
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ReferralStatus(str, enum.Enum):
    PENDIENTE = "pendiente"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"


class Referral(Base):
    """Derivacion de un Paciente desde un Doctor hacia otra especialidad."""

    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_specialty: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(300))
    status: Mapped[ReferralStatus] = mapped_column(
        Enum(ReferralStatus), default=ReferralStatus.PENDIENTE
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(), server_default=func.now())
