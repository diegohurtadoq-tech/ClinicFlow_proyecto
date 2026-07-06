"""Tests del resumen de metricas del dashboard."""

from __future__ import annotations

import datetime as dt

from app.models.waitlist import WaitlistPriority
from app.services.appointment_service import AppointmentService
from app.services.dashboard_service import DashboardService
from app.services.schedule_service import ScheduleService
from app.services.waitlist_service import WaitlistService


def _today_at(hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(dt.date.today(), dt.time(hour, minute))


def test_stats_count_todays_appointments_and_specialty(db_session, doctor, patient):
    appointments = AppointmentService()
    schedules = ScheduleService()
    # asegura que el doctor atienda hoy, sin importar que dia de la semana sea
    schedules.create_schedule(
        db_session, doctor.id, dt.date.today().weekday(), dt.time(0, 0), dt.time(23, 59)
    )

    moment = _today_at(9, 0)
    appt = appointments.create(db_session, patient.id, doctor.id, moment)
    appointments.confirm(db_session, appt.id)

    stats = DashboardService().get_stats(db_session)

    assert stats.appointments_today == 1
    assert stats.confirmed_today == 1
    assert stats.confirmed_percent == 100.0
    assert any(s.specialty == doctor.specialty and s.count == 1 for s in stats.specialties)


def test_stats_count_cancellations_today(db_session, doctor, patient, next_monday_10am):
    appointments = AppointmentService()
    appt = appointments.create(db_session, patient.id, doctor.id, next_monday_10am)
    appointments.cancel(db_session, appt.id)

    stats = DashboardService().get_stats(db_session)

    assert stats.cancellations_today == 1


def test_stats_waitlist_counts(db_session, doctor, patient, other_patient):
    waitlist = WaitlistService()
    waitlist.join(db_session, patient.id, specialty=doctor.specialty, priority=WaitlistPriority.ALTA)
    waitlist.join(db_session, other_patient.id, specialty=doctor.specialty, priority=WaitlistPriority.NORMAL)

    stats = DashboardService().get_stats(db_session)

    assert stats.waitlist_total == 2
    assert stats.waitlist_high_priority == 1


def test_doctor_status_activo_when_no_block_and_capacity_left(db_session, doctor):
    stats = DashboardService().get_stats(db_session)
    status = next(d for d in stats.doctors if d.id == doctor.id)
    assert status.status == "activo"


def test_doctor_status_bloqueada_when_blocked_now(db_session, doctor):
    schedules = ScheduleService()
    now = dt.datetime.now()
    schedules.create_block(
        db_session,
        doctor_id=doctor.id,
        start_datetime=now - dt.timedelta(hours=1),
        end_datetime=now + dt.timedelta(hours=1),
        reason="Capacitacion",
    )

    stats = DashboardService().get_stats(db_session)
    status = next(d for d in stats.doctors if d.id == doctor.id)
    assert status.status == "bloqueada"
