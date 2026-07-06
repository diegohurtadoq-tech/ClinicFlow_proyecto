"""Schemas Pydantic para Agenda medica (Schedule / ScheduleBlock)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class ScheduleCreate(BaseModel):
    doctor_id: int
    day_of_week: int
    start_time: dt.time
    end_time: dt.time
    slot_minutes: int = 30
    capacity: int = 1


class ScheduleResponse(BaseModel):
    id: int
    doctor_id: int
    day_of_week: int
    start_time: dt.time
    end_time: dt.time
    slot_minutes: int
    capacity: int

    model_config = {"from_attributes": True}


class ScheduleBlockCreate(BaseModel):
    doctor_id: int
    start_datetime: dt.datetime
    end_datetime: dt.datetime
    reason: str


class ScheduleBlockResponse(BaseModel):
    id: int
    doctor_id: int
    start_datetime: dt.datetime
    end_datetime: dt.datetime
    reason: str

    model_config = {"from_attributes": True}


class AvailabilitySlot(BaseModel):
    """Un cupo disponible concreto, calculado a partir de Schedule menos bloqueos/citas."""

    doctor_id: int
    start: dt.datetime
    end: dt.datetime
