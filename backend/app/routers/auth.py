"""
Rutas de autenticacion: registro de pacientes (autoservicio), login (admin
o paciente, el rol viene de la base de datos, no de lo que pida el cliente)
y verificacion de sesion.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_user
from ..auth.jwt_handler import create_access_token
from ..auth.security import hash_password, verify_password
from ..database import get_db
from ..exceptions import AuthenticationError, ClinicFlowError
from ..models.user import Patient, User
from ..schemas.auth import AuthResponse, CurrentUser, LoginRequest, RegisterPatientRequest

router = APIRouter(prefix="/api/auth", tags=["Autenticacion"])


class EmailAlreadyRegisteredError(ClinicFlowError):
    def __init__(self) -> None:
        super().__init__("Ese correo ya esta registrado.", status_code=409)


@router.post("/register", response_model=AuthResponse)
def register_patient(body: RegisterPatientRequest, db: Session = Depends(get_db)):
    """Autoservicio: cualquiera puede crear su propio perfil de Paciente."""
    if db.scalar(select(User).where(User.email == body.email)) is not None:
        raise EmailAlreadyRegisteredError()

    patient = Patient(
        name=body.name,
        email=body.email,
        rut=body.rut,
        telegram_id=body.telegram_id,
        password_hash=hash_password(body.password),
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    token = create_access_token(patient.id, patient.role)
    return AuthResponse(access_token=token, user=CurrentUser.model_validate(patient))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise AuthenticationError("Correo o contraseña incorrectos.")

    token = create_access_token(user.id, user.role)
    return AuthResponse(access_token=token, user=CurrentUser.model_validate(user))


@router.get("/me", response_model=CurrentUser)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
