"""
Servicio de reportes para el dashboard. Es de solo lectura (no aplica
reglas de negocio nuevas): agrega datos ya validados por los demas
Services para alimentar los paneles de metricas.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.appointment import Appointment, AppointmentStatus
from ..models.conversation import ConversationMessage
from ..models.schedule import Schedule, ScheduleBlock
from ..models.user import Doctor
from ..models.waitlist import WaitlistEntry, WaitlistPriority
from ..schemas.ai import Intent
from ..schemas.dashboard import ConversationsToday, DashboardStats, DoctorStatus, SpecialtyCount
from .schedule_service import ScheduleService

_INTENT_BUCKETS = {
    Intent.CREATE_APPOINTMENT.value: "agendamientos",
    Intent.CANCEL_APPOINTMENT.value: "cancelaciones",
    Intent.CHECK_AVAILABILITY.value: "consultas_disponibilidad",
    Intent.JOIN_WAITLIST.value: "lista_espera",
}


class DashboardService:
    """Agrega metricas operacionales para el panel principal."""

    def __init__(self, schedule_service: ScheduleService | None = None) -> None:
        self._schedules = schedule_service or ScheduleService()

    def _today_range(self) -> tuple[dt.datetime, dt.datetime]:
        today = dt.date.today()
        start = dt.datetime.combine(today, dt.time.min)
        end = start + dt.timedelta(days=1)
        return start, end

    def _appointments_today(self, db: Session) -> list[Appointment]:
        start, end = self._today_range()
        return list(
            db.scalars(
                select(Appointment).where(
                    Appointment.datetime_ >= start, Appointment.datetime_ < end
                )
            ).all()
        )

    def _cancellations_today(self, db: Session) -> int:
        start, end = self._today_range()
        return len(
            db.scalars(
                select(Appointment).where(
                    Appointment.cancelled_at >= start, Appointment.cancelled_at < end
                )
            ).all()
        )

    def _conversations_today(self, db: Session) -> ConversationsToday:
        start, end = self._today_range()
        messages = db.scalars(
            select(ConversationMessage).where(
                ConversationMessage.role == "assistant",
                ConversationMessage.created_at >= start,
                ConversationMessage.created_at < end,
            )
        ).all()
        buckets = {"agendamientos": 0, "cancelaciones": 0, "consultas_disponibilidad": 0, "lista_espera": 0}
        for m in messages:
            bucket = _INTENT_BUCKETS.get(m.intent or "")
            if bucket:
                buckets[bucket] += 1
        return ConversationsToday(total=len(messages), **buckets)

    def _doctor_status(self, db: Session, doctor: Doctor) -> DoctorStatus:
        now = dt.datetime.now()
        today = dt.date.today()
        weekday = today.weekday()

        schedules_today = list(
            db.scalars(
                select(Schedule).where(Schedule.doctor_id == doctor.id, Schedule.day_of_week == weekday)
            ).all()
        )

        blocked_now = self._schedules.is_blocked(db, doctor.id, now)

        available_slots_today = 0
        for schedule in schedules_today:
            slot = dt.datetime.combine(today, schedule.start_time)
            end = dt.datetime.combine(today, schedule.end_time)
            step = dt.timedelta(minutes=schedule.slot_minutes)
            while slot < end:
                if self._schedules.is_available(db, doctor.id, slot):
                    available_slots_today += 1
                slot += step

        if blocked_now:
            status = "bloqueada"
        elif schedules_today and available_slots_today == 0:
            status = "agenda_llena"
        else:
            status = "activo"

        return DoctorStatus(
            id=doctor.id,
            name=doctor.name,
            specialty=doctor.specialty,
            status=status,
            available_slots_today=available_slots_today,
        )

    def get_stats(self, db: Session) -> DashboardStats:
        appointments_today = self._appointments_today(db)
        confirmed_today = sum(1 for a in appointments_today if a.status == AppointmentStatus.CONFIRMADA)
        total_today = len(appointments_today)
        confirmed_percent = round((confirmed_today / total_today) * 100, 1) if total_today else 0.0

        specialty_counts: dict[str, int] = {}
        doctors_by_id = {d.id: d for d in db.scalars(select(Doctor)).all()}
        for appt in appointments_today:
            doctor = doctors_by_id.get(appt.doctor_id)
            specialty = doctor.specialty if doctor and doctor.specialty else "Sin especialidad"
            specialty_counts[specialty] = specialty_counts.get(specialty, 0) + 1

        waitlist_entries = db.scalars(select(WaitlistEntry)).all()

        return DashboardStats(
            appointments_today=total_today,
            confirmed_today=confirmed_today,
            confirmed_percent=confirmed_percent,
            waitlist_total=len(waitlist_entries),
            waitlist_high_priority=sum(1 for w in waitlist_entries if w.priority == WaitlistPriority.ALTA),
            cancellations_today=self._cancellations_today(db),
            specialties=[SpecialtyCount(specialty=k, count=v) for k, v in specialty_counts.items()],
            conversations_today=self._conversations_today(db),
            doctors=[self._doctor_status(db, d) for d in doctors_by_id.values()],
        )
