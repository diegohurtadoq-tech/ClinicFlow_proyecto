"""Rutas REST para Agenda medica: Schedule, ScheduleBlock y disponibilidad."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth.dependencies import require_role
from ..database import get_db
from ..schemas.schedule import (
    ScheduleBlockCreate,
    ScheduleBlockResponse,
    ScheduleCreate,
    ScheduleResponse,
)
from ..services.schedule_service import ScheduleService

router = APIRouter(prefix="/api", tags=["Agenda"], dependencies=[Depends(require_role("admin", "doctor"))])
_service = ScheduleService()


@router.post("/schedules", response_model=ScheduleResponse)
def create_schedule(body: ScheduleCreate, db: Session = Depends(get_db)):
    return _service.create_schedule(
        db,
        doctor_id=body.doctor_id,
        day_of_week=body.day_of_week,
        start_time=body.start_time,
        end_time=body.end_time,
        slot_minutes=body.slot_minutes,
        capacity=body.capacity,
    )


@router.post("/schedule-blocks", response_model=ScheduleBlockResponse)
def create_schedule_block(body: ScheduleBlockCreate, db: Session = Depends(get_db)):
    return _service.create_block(
        db,
        doctor_id=body.doctor_id,
        start_datetime=body.start_datetime,
        end_datetime=body.end_datetime,
        reason=body.reason,
    )


@router.get("/schedules/availability")
def check_availability(
    doctor_id: int = Query(...),
    moment: dt.datetime = Query(..., alias="datetime"),
    db: Session = Depends(get_db),
):
    return {"doctor_id": doctor_id, "datetime": moment, "available": _service.is_available(db, doctor_id, moment)}
