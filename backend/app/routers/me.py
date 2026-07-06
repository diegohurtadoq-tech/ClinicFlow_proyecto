"""
Rutas para que un Paciente autenticado consulte SUS PROPIOS datos. A
diferencia de los routers administrativos, aqui no se recibe ningun id por
parametro: todo se filtra por el usuario resuelto desde el token, para que
un paciente nunca pueda ver datos de otro cambiando un id en la URL.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user, require_role
from ..database import get_db
from ..models.appointment import Appointment
from ..models.user import Doctor, User
from ..models.waitlist import WaitlistEntry
from ..schemas.appointment import AppointmentResponse
from ..schemas.waitlist import WaitlistEntryResponse

router = APIRouter(prefix="/api/me", tags=["Mi cuenta"], dependencies=[Depends(require_role("patient"))])


@router.get("/appointments", response_model=list[AppointmentResponse])
def my_appointments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    appointments = db.scalars(
        select(Appointment).where(Appointment.patient_id == current_user.id)
    ).all()
    doctors_by_id = {d.id: d for d in db.scalars(select(Doctor)).all()}
    return [
        AppointmentResponse(
            id=a.id,
            patient_id=a.patient_id,
            doctor_id=a.doctor_id,
            datetime_=a.datetime_,
            status=a.status,
            notes=a.notes,
            patient_name=current_user.name,
            doctor_name=(doctors_by_id.get(a.doctor_id).name if doctors_by_id.get(a.doctor_id) else None),
            specialty=(doctors_by_id.get(a.doctor_id).specialty if doctors_by_id.get(a.doctor_id) else None),
        )
        for a in appointments
    ]


@router.get("/waitlist", response_model=list[WaitlistEntryResponse])
def my_waitlist(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(WaitlistEntry).where(WaitlistEntry.patient_id == current_user.id)
    ).all()
