"""Tests de la maquina de estados de Citas y deteccion de conflictos de agenda."""

from __future__ import annotations

import datetime as dt

import pytest

from app.exceptions import ClinicFlowError, InvalidStateTransitionError, ScheduleConflictError, SecurityViolationError
from app.models.appointment import AppointmentStatus
from app.services.appointment_service import AppointmentService


class FakeNotificationService:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    def notify(self, patient_id: int, message: str) -> None:
        self.sent_messages.append((patient_id, message))


def test_create_appointment_within_schedule_succeeds(db_session, doctor, patient, next_monday_10am):
    service = AppointmentService()
    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    assert appt.status == AppointmentStatus.PENDIENTE
    assert appt.id is not None


def test_create_appointment_in_past_fails(db_session, doctor, patient):
    service = AppointmentService()
    past_moment = dt.datetime.now() - dt.timedelta(hours=1)
    with pytest.raises(ClinicFlowError, match="No es posible agendar o modificar citas en una fecha u hora pasada"):
        service.create(db_session, patient.id, doctor.id, past_moment)


def test_create_appointment_outside_schedule_fails(db_session, doctor, patient, next_monday_10am):
    service = AppointmentService()
    outside_hours = next_monday_10am.replace(hour=22)
    with pytest.raises(ScheduleConflictError):
        service.create(db_session, patient.id, doctor.id, outside_hours)


def test_double_booking_same_slot_fails(db_session, doctor, patient, other_patient, next_monday_10am):
    service = AppointmentService()
    service.create(db_session, patient.id, doctor.id, next_monday_10am)
    with pytest.raises(ScheduleConflictError):
        service.create(db_session, other_patient.id, doctor.id, next_monday_10am)


def test_cancel_then_recreate_same_slot_succeeds(db_session, doctor, patient, other_patient, next_monday_10am):
    service = AppointmentService()
    first = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    service.cancel(db_session, first.id)
    # tras cancelar, el cupo vuelve a estar libre
    second = service.create(db_session, other_patient.id, doctor.id, next_monday_10am)
    assert second.status == AppointmentStatus.PENDIENTE


def test_invalid_transition_on_terminal_state_raises(db_session, doctor, patient, next_monday_10am):
    service = AppointmentService()
    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    service.cancel(db_session, appt.id)
    with pytest.raises(InvalidStateTransitionError):
        service.confirm(db_session, appt.id)


def test_reschedule_creates_new_pending_appointment(db_session, doctor, patient, next_monday_10am):
    service = AppointmentService()
    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    new_moment = next_monday_10am + dt.timedelta(days=1)  # martes 10:00, dentro de agenda
    rescheduled = service.reschedule(db_session, appt.id, new_moment)

    assert rescheduled.status == AppointmentStatus.PENDIENTE
    assert rescheduled.datetime_ == new_moment

    db_session.refresh(appt)
    assert appt.status == AppointmentStatus.REAGENDADA
    assert appt.rescheduled_to_id == rescheduled.id


def test_reschedule_in_past_fails(db_session, doctor, patient, next_monday_10am):
    service = AppointmentService()
    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    past_moment = dt.datetime.now() - dt.timedelta(hours=1)
    with pytest.raises(ClinicFlowError, match="No es posible agendar o modificar citas en una fecha u hora pasada"):
        service.reschedule(db_session, appt.id, past_moment)


def test_cancel_rejects_mismatched_owner(db_session, doctor, patient, other_patient, next_monday_10am):
    service = AppointmentService()
    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    with pytest.raises(SecurityViolationError):
        service.cancel(db_session, appt.id, requesting_patient_id=other_patient.id)


def test_cancel_notifies_patient_when_telegram_is_linked(db_session, doctor, patient, next_monday_10am):
    notifications = FakeNotificationService()
    service = AppointmentService(notification_service=notifications)
    patient.telegram_id = "123456"
    db_session.add(patient)
    db_session.flush()

    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    service.cancel(db_session, appt.id)

    assert notifications.sent_messages
    patient_id, message = notifications.sent_messages[-1]
    assert patient_id == patient.id
    assert "cancelada" in message.lower()


def test_reschedule_notifies_patient_when_telegram_is_linked(db_session, doctor, patient, next_monday_10am):
    notifications = FakeNotificationService()
    service = AppointmentService(notification_service=notifications)
    patient.telegram_id = "123456"
    db_session.add(patient)
    db_session.flush()

    appt = service.create(db_session, patient.id, doctor.id, next_monday_10am)
    new_moment = next_monday_10am + dt.timedelta(days=1)
    service.reschedule(db_session, appt.id, new_moment)

    assert notifications.sent_messages
    patient_id, message = notifications.sent_messages[-1]
    assert patient_id == patient.id
    assert "reprogramada" in message.lower() or "modificada" in message.lower()
