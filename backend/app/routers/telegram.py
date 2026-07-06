"""
Router de Telegram: endpoints para generar codigos de vinculacion.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user, require_role
from ..database import get_db
from ..exceptions import ClinicFlowError
from ..models.user import Patient, User
from ..telegram.authenticator import PatientAuthenticator

router = APIRouter(prefix="/api/telegram", tags=["telegram"])

_authenticator = PatientAuthenticator()


class LinkCodeResponse(BaseModel):
    """Respuesta con codigo de vinculacion."""

    code: str
    expires_in_minutes: int
    instructions: str


@router.post("/link-code", response_model=LinkCodeResponse)
def generate_link_code(
    current_user: User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
) -> LinkCodeResponse:
    """Genera un codigo de vinculacion para el paciente autenticado.

    El codigo expira en 10 minutos y puede ser usado una sola vez para
    vincular la cuenta del paciente con Telegram.
    """
    try:
        code = _authenticator.generate_link_code(db, current_user.id)

        return LinkCodeResponse(
            code=code,
            expires_in_minutes=10,
            instructions=(
                f"Envia este codigo al bot de Telegram:\n"
                f"/start {code}\n\n"
                f"El codigo expira en 10 minutos."
            ),
        )

    except ClinicFlowError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
