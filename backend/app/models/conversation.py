"""
Registro de conversaciones del asistente IA. Cada `Conversation` pertenece
a un paciente y un canal (web, telegram); cada turno se guarda como un
`ConversationMessage`, incluyendo la intencion extraida por ActionAI y la
accion finalmente tomada (o el motivo de rechazo del ActionGuard).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class Conversation(Base):
    """Una conversacion entre un Paciente y el asistente IA."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(20), default="web")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(), server_default=func.now())

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.created_at",
    )


class ConversationMessage(Base):
    """Un turno dentro de una Conversation: mensaje de usuario o respuesta del asistente."""

    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(String(2000))
    intent: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action_taken: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(), server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
