"""Rutas REST minimas para Doctores (CRUD simple; sin reglas de negocio propias)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.dependencies import require_role
from ..database import get_db
from ..exceptions import NotFoundError
from ..models.user import Doctor
from ..schemas.user import DoctorCreate, DoctorResponse

router = APIRouter(
    prefix="/api/doctors", tags=["Doctores"], dependencies=[Depends(require_role("admin"))]
)


def _get_doctor(db: Session, doctor_id: int) -> Doctor:
    doctor = db.get(Doctor, doctor_id)
    if doctor is None:
        raise NotFoundError(f"No existe el doctor {doctor_id}.")
    return doctor


@router.get("", response_model=list[DoctorResponse])
def list_doctors(db: Session = Depends(get_db)):
    return db.scalars(select(Doctor)).all()


@router.post("", response_model=DoctorResponse)
def create_doctor(body: DoctorCreate, db: Session = Depends(get_db)):
    doctor = Doctor(name=body.name, email=body.email, specialty=body.specialty)
    db.add(doctor)
    db.commit()
    db.refresh(doctor)
    return doctor


@router.delete("/{doctor_id}", response_model=DoctorResponse)
def deactivate_doctor(doctor_id: int, db: Session = Depends(get_db)):
    """"Elimina" al doctor desactivandolo (ver Doctor.deactivate): deja de
    ofrecerse para nuevas citas, pero su historial clinico no se borra."""
    doctor = _get_doctor(db, doctor_id)
    doctor.deactivate()
    db.commit()
    db.refresh(doctor)
    return doctor
