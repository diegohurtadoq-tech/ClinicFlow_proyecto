"""Schemas Pydantic para Agenda medica (Schedule / ScheduleBlock)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, model_validator


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
    start_datetime: dt.datetime | None = None
    end_datetime: dt.datetime | None = None
    start_date: str | dt.date | None = None
    end_date: str | dt.date | None = None
    start_time: str | dt.time | None = None
    end_time: str | dt.time | None = None
    reason: str

    @model_validator(mode="before")
    @classmethod
    def normalize_datetimes(cls, values):
        if not isinstance(values, dict):
            return values

        normalized = dict(values)
        start_datetime = normalized.get("start_datetime")
        end_datetime = normalized.get("end_datetime")

        if start_datetime is None and (
            normalized.get("start_date") is not None or normalized.get("start_time") is not None
        ):
            start_datetime = cls._combine_datetime(normalized.get("start_date"), normalized.get("start_time"))

        if end_datetime is None and (
            normalized.get("end_date") is not None or normalized.get("end_time") is not None
        ):
            end_datetime = cls._combine_datetime(normalized.get("end_date"), normalized.get("end_time"))

        normalized["start_datetime"] = start_datetime
        normalized["end_datetime"] = end_datetime
        return normalized

    @model_validator(mode="after")
    def validate_datetime_range(self):
        if self.start_datetime is None or self.end_datetime is None:
            raise ValueError("Se requieren start_datetime/end_datetime o start_date/start_time/end_date/end_time.")
        if self.end_datetime <= self.start_datetime:
            raise ValueError("La fecha/hora de término debe ser posterior a la de inicio.")
        return self

    @staticmethod
    def _combine_datetime(date_value, time_value) -> dt.datetime:
        if date_value is None:
            raise ValueError("Falta la fecha del bloqueo.")
        if time_value is None:
            raise ValueError("Falta la hora del bloqueo.")

        if isinstance(date_value, dt.datetime):
            date_obj = date_value.date()
        elif isinstance(date_value, dt.date):
            date_obj = date_value
        else:
            date_obj = dt.date.fromisoformat(str(date_value))

        if isinstance(time_value, dt.time):
            time_obj = time_value
        else:
            time_text = str(time_value).strip()
            if len(time_text) == 5 and ":" in time_text:
                time_obj = dt.datetime.strptime(time_text, "%H:%M").time()
            else:
                time_obj = dt.datetime.fromisoformat(time_text).time()

        return dt.datetime.combine(date_obj, time_obj)


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
