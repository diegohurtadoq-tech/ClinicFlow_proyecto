"""Schemas Pydantic para registro/login."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterPatientRequest(BaseModel):
    name: str
    email: str
    password: str = Field(..., min_length=6)
    rut: str | None = None
    telegram_id: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class CurrentUser(BaseModel):
    id: int
    name: str
    email: str
    role: str
    telegram_id: str | None = None

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: CurrentUser
