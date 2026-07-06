"""Rutas REST para Citas. Toda la logica vive en AppointmentService."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.dependencies import require_role
from ..database import get_db
from ..models.appointment import Appointment
from ..models.user import Doctor, Patient
from ..schemas.appointment import AppointmentCreate, AppointmentReschedule, AppointmentResponse
from ..services.appointment_service import AppointmentService

router = APIRouter(
    prefix="/api/appointments", tags=["Citas"], dependencies=[Depends(require_role("admin"))]
)
_service = AppointmentService()


def _enrich(appt: Appointment, patients_by_id: dict, doctors_by_id: dict) -> AppointmentResponse:
    """Construye la respuesta uniendo nombre de paciente/doctor y especialidad."""
    patient = patients_by_id.get(appt.patient_id)
    doctor = doctors_by_id.get(appt.doctor_id)
    return AppointmentResponse(
        id=appt.id,
        patient_id=appt.patient_id,
        doctor_id=appt.doctor_id,
        datetime_=appt.datetime_,
        status=appt.status,
        notes=appt.notes,
        patient_name=patient.name if patient else None,
        doctor_name=doctor.name if doctor else None,
        specialty=doctor.specialty if doctor else None,
    )


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(db: Session = Depends(get_db)):
    appointments = db.scalars(select(Appointment)).all()
    patients_by_id = {p.id: p for p in db.scalars(select(Patient)).all()}
    doctors_by_id = {d.id: d for d in db.scalars(select(Doctor)).all()}
    return [_enrich(a, patients_by_id, doctors_by_id) for a in appointments]


@router.post("", response_model=AppointmentResponse)
def create_appointment(body: AppointmentCreate, db: Session = Depends(get_db)):
    return _service.create(
        db,
        patient_id=body.patient_id,
        doctor_id=body.doctor_id,
        moment=body.datetime_,
        notes=body.notes,
    )


@router.post("/{appointment_id}/confirm", response_model=AppointmentResponse)
def confirm_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return _service.confirm(db, appointment_id)


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db)):
    return _service.cancel(db, appointment_id)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentResponse)
def reschedule_appointment(
    appointment_id: int, body: AppointmentReschedule, db: Session = Depends(get_db)
):
    return _service.reschedule(db, appointment_id, body.new_datetime)
