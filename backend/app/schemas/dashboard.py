"""Schemas Pydantic para el resumen del dashboard (GET /api/dashboard/stats)."""

from __future__ import annotations

from pydantic import BaseModel


class SpecialtyCount(BaseModel):
    specialty: str
    count: int


class ConversationsToday(BaseModel):
    total: int
    agendamientos: int
    cancelaciones: int
    consultas_disponibilidad: int
    lista_espera: int


class DoctorStatus(BaseModel):
    id: int
    name: str
    specialty: str | None
    status: str  # "activo" | "agenda_llena" | "bloqueada"
    available_slots_today: int


class DashboardStats(BaseModel):
    appointments_today: int
    confirmed_today: int
    confirmed_percent: float
    waitlist_total: int
    waitlist_high_priority: int
    cancellations_today: int
    specialties: list[SpecialtyCount]
    conversations_today: ConversationsToday
    doctors: list[DoctorStatus]
