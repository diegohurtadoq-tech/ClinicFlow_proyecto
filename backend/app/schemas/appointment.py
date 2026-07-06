"""Schemas Pydantic para el endpoint de Citas."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from ..models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: int
    datetime_: dt.datetime = Field(alias="datetime")
    notes: str | None = None

    model_config = {"populate_by_name": True}


class AppointmentReschedule(BaseModel):
    new_datetime: dt.datetime


class AppointmentResponse(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    datetime_: dt.datetime = Field(serialization_alias="datetime")
    status: AppointmentStatus
    notes: str | None = None
    # Campos "enriquecidos" (no viven en la tabla appointments): se completan
    # en el router uniendo con Patient/Doctor, para que el dashboard no tenga
    # que hacer N llamadas adicionales solo para mostrar nombres.
    patient_name: str | None = None
    doctor_name: str | None = None
    specialty: str | None = None

    model_config = {"from_attributes": True}
