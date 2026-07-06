"""
Servicio de Lista de espera: inscripcion, priorizacion y reasignacion
automatica de cupos liberados.

Nota de diseno: `try_fill_slot` recibe la instancia de `AppointmentService`
como parametro en lugar de importarla a nivel de modulo, para evitar un
ciclo de imports (AppointmentService ya depende de WaitlistService al
cancelar). Es composicion explicita, no una dependencia oculta.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..exceptions import NotFoundError, ScheduleConflictError
from ..models.appointment import Appointment
from ..models.schedule import Schedule
from ..models.user import Doctor
from ..models.waitlist import WaitlistEntry, WaitlistPriority
from .notification_service import NotificationService
from .schedule_service import ScheduleService

if TYPE_CHECKING:
    from .appointment_service import AppointmentService


class WaitlistService:
    """Logica de negocio sobre la lista de espera."""

    def __init__(
        self,
        notification_service: NotificationService | None = None,
        schedule_service: ScheduleService | None = None,
    ) -> None:
        self._notifications = notification_service or NotificationService()
        self._schedules = schedule_service or ScheduleService()

    def join(
        self,
        db: Session,
        patient_id: int,
        specialty: str,
        doctor_id: int | None = None,
        priority: WaitlistPriority = WaitlistPriority.NORMAL,
    ) -> WaitlistEntry:
        entry = WaitlistEntry(
            patient_id=patient_id,
            specialty=specialty,
            doctor_id=doctor_id,
            priority=priority,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry

    def remove(self, db: Session, entry_id: int) -> None:
        entry = db.get(WaitlistEntry, entry_id)
        if entry is not None:
            db.delete(entry)
            db.commit()

    def _candidates(self, db: Session, doctor_id: int) -> list[WaitlistEntry]:
        entries = db.scalars(
            select(WaitlistEntry).where(
                (WaitlistEntry.doctor_id == doctor_id) | (WaitlistEntry.doctor_id.is_(None))
            )
        ).all()
        return sorted(entries, key=lambda e: e.sort_key())

    def try_fill_slot(
        self,
        db: Session,
        appointment_service: "AppointmentService",
        doctor_id: int,
        moment: dt.datetime,
    ) -> Appointment | None:
        """Tras liberarse un cupo, ofrece el horario al paciente de mayor prioridad en espera.

        Crea directamente una nueva cita PENDIENTE (en un sistema real esto
        seria una oferta con confirmacion del paciente vía notificacion;
        se simplifica aqui y se deja el aviso a NotificationService).
        """
        candidates = self._candidates(db, doctor_id)
        if not candidates:
            return None

        winner = candidates[0]
        new_appointment = appointment_service.create(
            db,
            patient_id=winner.patient_id,
            doctor_id=doctor_id,
            moment=moment,
            notes="Asignado automaticamente desde lista de espera.",
        )
        self._notifications.notify(
            winner.patient_id,
            f"Se liberó un cupo y se te asignó una hora el {moment.isoformat()}.",
        )
        db.delete(winner)
        db.commit()
        return new_appointment

    def assign_now(
        self,
        db: Session,
        entry_id: int,
        appointment_service: "AppointmentService",
        days_ahead: int = 14,
    ) -> Appointment:
        """Busca el primer cupo disponible (hoy en adelante) para esta inscripcion
        y crea la cita de inmediato -- es la accion manual detras del boton
        'Asignar hora disponible' del dashboard (a diferencia de `try_fill_slot`,
        que se dispara automaticamente al cancelarse una cita)."""
        entry = db.get(WaitlistEntry, entry_id)
        if entry is None:
            raise NotFoundError(f"No existe la inscripcion {entry_id} en lista de espera.")

        if entry.doctor_id is not None:
            doctor_ids = [entry.doctor_id]
        else:
            doctor_ids = [
                d.id for d in db.scalars(select(Doctor).where(Doctor.specialty == entry.specialty)).all()
            ]
        if not doctor_ids:
            raise NotFoundError(f"No hay doctores de la especialidad '{entry.specialty}'.")

        now = dt.datetime.now()
        for day_offset in range(days_ahead):
            day = now.date() + dt.timedelta(days=day_offset)
            for doctor_id in doctor_ids:
                schedules = db.scalars(
                    select(Schedule).where(
                        Schedule.doctor_id == doctor_id, Schedule.day_of_week == day.weekday()
                    )
                ).all()
                for schedule in schedules:
                    slot = dt.datetime.combine(day, schedule.start_time)
                    end = dt.datetime.combine(day, schedule.end_time)
                    step = dt.timedelta(minutes=schedule.slot_minutes)
                    while slot < end:
                        if slot > now and self._schedules.is_available(db, doctor_id, slot):
                            new_appointment = appointment_service.create(
                                db,
                                patient_id=entry.patient_id,
                                doctor_id=doctor_id,
                                moment=slot,
                                notes="Asignado manualmente desde lista de espera.",
                            )
                            self._notifications.notify(
                                entry.patient_id, f"Se te asigno una hora el {slot.isoformat()}."
                            )
                            db.delete(entry)
                            db.commit()
                            return new_appointment
                        slot += step

        raise ScheduleConflictError(
            f"No se encontro un cupo disponible en los proximos {days_ahead} dias."
        )
