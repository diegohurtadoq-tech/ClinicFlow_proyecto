"""Schemas Pydantic para Pacientes y Doctores."""

from __future__ import annotations

from pydantic import BaseModel


class PatientCreate(BaseModel):
    name: str
    email: str
    rut: str | None = None
    telegram_id: str | None = None


class PatientResponse(BaseModel):
    id: int
    name: str
    email: str
    rut: str | None
    telegram_id: str | None

    model_config = {"from_attributes": True}


class DoctorCreate(BaseModel):
    name: str
    email: str
    specialty: str


class DoctorResponse(BaseModel):
    id: int
    name: str
    email: str
    specialty: str | None
    is_active: bool

    model_config = {"from_attributes": True}
