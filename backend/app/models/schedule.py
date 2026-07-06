"""
Agenda medica: `Schedule` define bloques de atencion recurrentes por dia de
la semana para un Doctor; `ScheduleBlock` representa un bloqueo o suspension
puntual (vacaciones, capacitacion, reunion) sobre un rango de fecha/hora.

Composicion: si un Doctor se elimina, sus Schedule y ScheduleBlock se
eliminan en cascada (ver `cascade="all, delete-orphan"` en `Doctor.schedules`
y la FK de ScheduleBlock).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Schedule(Base):
    """Bloque de atencion recurrente: un Doctor atiende un dia de la semana en un rango horario."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    day_of_week: Mapped[int] = mapped_column()  # 0=lunes ... 6=domingo
    start_time: Mapped[dt.time] = mapped_column()
    end_time: Mapped[dt.time] = mapped_column()
    slot_minutes: Mapped[int] = mapped_column(default=30)
    capacity: Mapped[int] = mapped_column(default=1)  # pacientes simultaneos por slot

    doctor: Mapped["Doctor"] = relationship(back_populates="schedules")  # noqa: F821

    def covers(self, moment: dt.datetime) -> bool:
        """Indica si `moment` cae dentro de este bloque recurrente."""
        return (
            moment.weekday() == self.day_of_week
            and self.start_time <= moment.time() < self.end_time
        )

    def __repr__(self) -> str:
        return (
            f"Schedule(doctor_id={self.doctor_id}, day={self.day_of_week}, "
            f"{self.start_time}-{self.end_time})"
        )


class ScheduleBlock(Base):
    """Bloqueo o suspension puntual de la agenda de un Doctor en un rango de fecha/hora."""

    __tablename__ = "schedule_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    start_datetime: Mapped[dt.datetime] = mapped_column()
    end_datetime: Mapped[dt.datetime] = mapped_column()
    reason: Mapped[str] = mapped_column(String(200))

    def overlaps(self, moment: dt.datetime) -> bool:
        """Indica si `moment` cae dentro del rango bloqueado."""
        return self.start_datetime <= moment < self.end_datetime
