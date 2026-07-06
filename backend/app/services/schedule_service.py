"""
Servicio de Agenda medica: disponibilidad, bloqueos y suspensiones.

Esta es la unica fuente de verdad sobre si un Doctor puede atender en un
momento dado. AppointmentService delega aqui antes de crear o reagendar
una cita.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.appointment import Appointment, AppointmentStatus
from ..models.schedule import Schedule, ScheduleBlock
from ..models.user import Doctor


class ScheduleService:
    """Logica de disponibilidad sobre Schedule/ScheduleBlock."""

    def create_schedule(
        self,
        db: Session,
        doctor_id: int,
        day_of_week: int,
        start_time: dt.time,
        end_time: dt.time,
        slot_minutes: int = 30,
        capacity: int = 1,
    ) -> Schedule:
        schedule = Schedule(
            doctor_id=doctor_id,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            slot_minutes=slot_minutes,
            capacity=capacity,
        )
        db.add(schedule)
        db.commit()
        db.refresh(schedule)
        return schedule

    def create_block(
        self,
        db: Session,
        doctor_id: int,
        start_datetime: dt.datetime,
        end_datetime: dt.datetime,
        reason: str,
    ) -> ScheduleBlock:
        block = ScheduleBlock(
            doctor_id=doctor_id,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            reason=reason,
        )
        db.add(block)
        db.commit()
        db.refresh(block)
        return block

    def _is_within_recurring_schedule(self, db: Session, doctor_id: int, moment: dt.datetime) -> bool:
        schedules = db.scalars(
            select(Schedule).where(Schedule.doctor_id == doctor_id)
        ).all()
        return any(s.covers(moment) for s in schedules)

    def is_blocked(self, db: Session, doctor_id: int, moment: dt.datetime) -> bool:
        """Indica si existe un ScheduleBlock del Doctor que cubra `moment` (API publica)."""
        blocks = db.scalars(
            select(ScheduleBlock).where(ScheduleBlock.doctor_id == doctor_id)
        ).all()
        return any(b.overlaps(moment) for b in blocks)

    def _active_appointment_count(self, db: Session, doctor_id: int, moment: dt.datetime) -> int:
        appts = db.scalars(
            select(Appointment).where(
                Appointment.doctor_id == doctor_id,
                Appointment.datetime_ == moment,
            )
        ).all()
        return sum(1 for a in appts if a.is_active())

    def _capacity_at(self, db: Session, doctor_id: int, moment: dt.datetime) -> int:
        schedules = db.scalars(
            select(Schedule).where(Schedule.doctor_id == doctor_id)
        ).all()
        matching = [s for s in schedules if s.covers(moment)]
        return max((s.capacity for s in matching), default=0)

    def is_available(self, db: Session, doctor_id: int, moment: dt.datetime) -> bool:
        """Indica si el Doctor puede atender en `moment`: activo, dentro de su
        agenda, sin bloqueo activo, y sin exceder la capacidad del slot."""
        doctor = db.get(Doctor, doctor_id)
        if doctor is None or not doctor.is_active:
            return False
        if not self._is_within_recurring_schedule(db, doctor_id, moment):
            return False
        if self.is_blocked(db, doctor_id, moment):
            return False
        capacity = self._capacity_at(db, doctor_id, moment)
        return self._active_appointment_count(db, doctor_id, moment) < capacity

    def available_doctors_for_specialty(
        self, db: Session, specialty: str, moment: dt.datetime
    ) -> list[Doctor]:
        """Doctores de `specialty` (comparacion sin distinguir mayusculas) que
        pueden atender en `moment`. Permite responder consultas de
        disponibilidad por especialidad cuando el paciente no menciona un
        medico en particular."""
        doctors = db.scalars(
            select(Doctor).where(func.lower(Doctor.specialty) == specialty.strip().lower())
        ).all()
        return [d for d in doctors if self.is_available(db, d.id, moment)]
