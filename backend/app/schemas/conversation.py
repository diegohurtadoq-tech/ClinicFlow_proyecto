"""Schemas Pydantic para el endpoint conversacional."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    """Cuerpo de POST /api/conversation/{patient_id}/message."""

    message: str = Field(..., min_length=1, max_length=2000)
    channel: str = "web"


class MessageResponse(BaseModel):
    """Respuesta enviada de vuelta al paciente."""

    conversation_id: int
    reply: str
    intent: str | None = None
    action_taken: str | None = None


class ConversationMessageResponse(BaseModel):
    id: int
    role: str
    content: str
    intent: str | None
    action_taken: str | None
    created_at: dt.datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: int
    patient_id: int
    channel: str
    messages: list[ConversationMessageResponse]
    patient_name: str | None = None

    model_config = {"from_attributes": True}
