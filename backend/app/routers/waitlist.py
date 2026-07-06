"""Rutas REST para Lista de espera."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.dependencies import require_role
from ..database import get_db
from ..models.waitlist import WaitlistEntry
from ..schemas.appointment import AppointmentResponse
from ..schemas.waitlist import WaitlistEntryCreate, WaitlistEntryResponse
from ..services.appointment_service import AppointmentService
from ..services.waitlist_service import WaitlistService

router = APIRouter(
    prefix="/api/waitlist", tags=["Lista de espera"], dependencies=[Depends(require_role("admin"))]
)
_appointments = AppointmentService()
_service = WaitlistService()


@router.get("", response_model=list[WaitlistEntryResponse])
def list_waitlist(db: Session = Depends(get_db)):
    return db.scalars(select(WaitlistEntry)).all()


@router.post("", response_model=WaitlistEntryResponse)
def join_waitlist(body: WaitlistEntryCreate, db: Session = Depends(get_db)):
    return _service.join(
        db,
        patient_id=body.patient_id,
        specialty=body.specialty,
        doctor_id=body.doctor_id,
        priority=body.priority,
    )


@router.delete("/{entry_id}", status_code=204)
def remove_from_waitlist(entry_id: int, db: Session = Depends(get_db)):
    _service.remove(db, entry_id)


@router.post("/{entry_id}/assign", response_model=AppointmentResponse)
def assign_waitlist_slot(entry_id: int, db: Session = Depends(get_db)):
    return _service.assign_now(db, entry_id, _appointments)
