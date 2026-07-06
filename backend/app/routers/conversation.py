"""
Ruta REST conversacional: punto de entrada de prueba para el flujo de las
dos IAs (sin Telegram todavia). Cada llamada equivale a un mensaje que un
paciente enviaria por el canal correspondiente.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.action_ai import ActionAI
from ..ai.front_desk_ai import FrontDeskAI
from ..ai.llm_client import OpenRouterClient
from ..ai.orchestrator import ConversationOrchestrator
from ..auth.dependencies import require_role
from ..database import get_db
from ..models.conversation import Conversation
from ..models.user import Patient, User
from ..schemas.conversation import ConversationResponse, MessageRequest, MessageResponse

router = APIRouter(prefix="/api/conversation", tags=["Conversacion IA"])
# Router separado (sin el singular "conversation/message" delante) para exponer
# el listado en /api/conversations, consumido por el dashboard del administrador.
list_router = APIRouter(
    prefix="/api/conversations",
    tags=["Conversacion IA"],
    dependencies=[Depends(require_role("admin"))],
)


def get_orchestrator() -> ConversationOrchestrator:
    """Construye el orquestador con clientes reales de OpenRouter para ambas IAs."""
    llm_client = OpenRouterClient()
    return ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(llm_client),
        action_ai=ActionAI(llm_client),
    )


@router.post("/message", response_model=MessageResponse)
def send_message(
    body: MessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("patient")),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
):
    """El patient_id viene SIEMPRE del token verificado, nunca de la solicitud:
    asi se cierra el hueco de suplantacion que existia cuando el id viajaba
    como parametro de URL sin ninguna autenticacion detras."""
    return orchestrator.handle_message(db, current_user.id, body.message, body.channel)


@list_router.get("", response_model=list[ConversationResponse])
def list_conversations(db: Session = Depends(get_db)):
    """Lista todas las conversaciones, para el panel 'Conversaciones IA' del dashboard."""
    conversations = db.scalars(select(Conversation)).all()
    patients_by_id = {p.id: p for p in db.scalars(select(Patient)).all()}
    results = []
    for c in conversations:
        response = ConversationResponse.model_validate(c)
        patient = patients_by_id.get(c.patient_id)
        response.patient_name = patient.name if patient else None
        results.append(response)
    return results
