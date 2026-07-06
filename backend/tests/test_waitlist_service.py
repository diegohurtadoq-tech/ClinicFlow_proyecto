"""Tests de lista de espera: priorizacion y reasignacion automatica al cancelar."""

from __future__ import annotations

from app.models.appointment import Appointment, AppointmentStatus
from app.models.waitlist import WaitlistEntry, WaitlistPriority
from app.services.appointment_service import AppointmentService
from app.services.waitlist_service import WaitlistService


def test_join_waitlist_creates_entry(db_session, patient):
    service = WaitlistService()
    entry = service.join(db_session, patient.id, specialty="Cardiología")
    assert entry.id is not None
    assert entry.priority == WaitlistPriority.NORMAL


def test_high_priority_is_served_before_normal(db_session, doctor, patient, other_patient, next_monday_10am):
    appointments = AppointmentService()
    waitlist = WaitlistService()

    appt = appointments.create(db_session, patient.id, doctor.id, next_monday_10am)

    waitlist.join(db_session, other_patient.id, specialty=doctor.specialty, doctor_id=doctor.id, priority=WaitlistPriority.NORMAL)
    waitlist.join(db_session, patient.id, specialty=doctor.specialty, doctor_id=doctor.id, priority=WaitlistPriority.ALTA)

    appointments.cancel(db_session, appt.id)

    new_appt = (
        db_session.query(Appointment)
        .filter(Appointment.doctor_id == doctor.id, Appointment.datetime_ == next_monday_10am)
        .filter(Appointment.status == AppointmentStatus.PENDIENTE)
        .one()
    )
    # el paciente de prioridad ALTA (mismo `patient`) debe ganar el cupo liberado
    assert new_appt.patient_id == patient.id
    assert db_session.query(WaitlistEntry).count() == 1  # solo queda el de prioridad normal


def test_assign_now_finds_next_free_slot(db_session, doctor, patient):
    appointments = AppointmentService()
    waitlist = WaitlistService()

    entry = waitlist.join(db_session, patient.id, specialty=doctor.specialty, doctor_id=doctor.id)

    new_appt = waitlist.assign_now(db_session, entry.id, appointments)

    assert new_appt.patient_id == patient.id
    assert new_appt.doctor_id == doctor.id
    assert new_appt.status == AppointmentStatus.PENDIENTE
    assert new_appt.datetime_.weekday() < 5  # lunes a viernes, dentro de la agenda del doctor
    assert db_session.query(WaitlistEntry).count() == 0


def test_assign_now_matches_by_specialty_when_no_doctor_pinned(db_session, doctor, patient):
    appointments = AppointmentService()
    waitlist = WaitlistService()

    entry = waitlist.join(db_session, patient.id, specialty=doctor.specialty)  # sin doctor_id

    new_appt = waitlist.assign_now(db_session, entry.id, appointments)

    assert new_appt.doctor_id == doctor.id
