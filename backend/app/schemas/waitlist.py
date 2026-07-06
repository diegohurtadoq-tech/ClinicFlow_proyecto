"""Schemas Pydantic para Lista de espera."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from ..models.waitlist import WaitlistPriority


class WaitlistEntryCreate(BaseModel):
    patient_id: int
    specialty: str
    doctor_id: int | None = None
    priority: WaitlistPriority = WaitlistPriority.NORMAL


class WaitlistEntryResponse(BaseModel):
    id: int
    patient_id: int
    specialty: str
    doctor_id: int | None
    priority: WaitlistPriority
    created_at: dt.datetime

    model_config = {"from_attributes": True}
