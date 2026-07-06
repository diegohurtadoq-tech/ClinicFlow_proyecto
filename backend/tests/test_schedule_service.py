"""Tests de disponibilidad de agenda: horario, bloqueos y capacidad."""

from __future__ import annotations

import datetime as dt

from app.schemas.schedule import ScheduleBlockCreate
from app.services.schedule_service import ScheduleService


def test_schedule_block_create_accepts_legacy_field_names():
    payload = {
        "doctor_id": 1,
        "start_date": "2026-08-01",
        "start_time": "09:00",
        "end_date": "2026-08-01",
        "end_time": "11:00",
        "reason": "Capacitación",
    }
    block = ScheduleBlockCreate.model_validate(payload)
    assert block.start_datetime == dt.datetime(2026, 8, 1, 9, 0)
    assert block.end_datetime == dt.datetime(2026, 8, 1, 11, 0)


def test_available_within_schedule(db_session, doctor, next_monday_10am):
    service = ScheduleService()
    assert service.is_available(db_session, doctor.id, next_monday_10am) is True


def test_not_available_outside_schedule_hours(db_session, doctor, next_monday_10am):
    service = ScheduleService()
    outside_hours = next_monday_10am.replace(hour=20)
    assert service.is_available(db_session, doctor.id, outside_hours) is False


def test_not_available_on_weekend(db_session, doctor, next_monday_10am):
    service = ScheduleService()
    saturday = next_monday_10am + dt.timedelta(days=5)
    assert service.is_available(db_session, doctor.id, saturday) is False


def test_not_available_when_blocked(db_session, doctor, next_monday_10am):
    service = ScheduleService()
    service.create_block(
        db_session,
        doctor_id=doctor.id,
        start_datetime=next_monday_10am.replace(hour=9),
        end_datetime=next_monday_10am.replace(hour=12),
        reason="Capacitacion",
    )
    assert service.is_available(db_session, doctor.id, next_monday_10am) is False


def test_not_available_when_doctor_deactivated(db_session, doctor, next_monday_10am):
    service = ScheduleService()
    doctor.deactivate()
    db_session.commit()
    assert service.is_available(db_session, doctor.id, next_monday_10am) is False


def test_deactivated_doctor_excluded_from_specialty_search(db_session, doctor, next_monday_10am):
    service = ScheduleService()
    doctor.deactivate()
    db_session.commit()
    assert service.available_doctors_for_specialty(
        db_session, doctor.specialty, next_monday_10am
    ) == []
