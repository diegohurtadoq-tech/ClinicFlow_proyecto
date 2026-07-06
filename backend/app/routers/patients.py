"""Rutas REST minimas para Pacientes (CRUD simple; sin reglas de negocio propias)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.dependencies import require_role
from ..database import get_db
from ..models.user import Patient
from ..schemas.user import PatientCreate, PatientResponse

router = APIRouter(
    prefix="/api/patients", tags=["Pacientes"], dependencies=[Depends(require_role("admin"))]
)


@router.get("", response_model=list[PatientResponse])
def list_patients(db: Session = Depends(get_db)):
    return db.scalars(select(Patient)).all()


@router.post("", response_model=PatientResponse)
def create_patient(body: PatientCreate, db: Session = Depends(get_db)):
    patient = Patient(
        name=body.name, email=body.email, rut=body.rut, telegram_id=body.telegram_id
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient
