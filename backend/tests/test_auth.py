"""
Tests de autenticacion/autorizacion: registro, login, y que las rutas
administrativas y las rutas "/api/me/*" respeten los roles y la
pertenencia de los datos.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.auth.security import verify_password
from app.database import get_db
from app.main import app
from app.models.appointment import Appointment, AppointmentStatus
from app.models.user import Patient


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register(client, email="ana@example.com", password="secreto123", name="Ana Torres"):
    return client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": password},
    )


def test_register_hashes_password_and_returns_token(client, db_session):
    response = _register(client)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "patient"
    assert "access_token" in body

    stored = db_session.query(Patient).filter_by(email="ana@example.com").one()
    assert stored.password_hash != "secreto123"
    assert verify_password("secreto123", stored.password_hash)


def test_register_duplicate_email_conflicts(client):
    _register(client)
    response = _register(client)
    assert response.status_code == 409


def test_login_success_returns_token(client):
    _register(client)
    response = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "secreto123"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "ana@example.com"


def test_login_wrong_password_rejected(client):
    _register(client)
    response = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "incorrecta"})
    assert response.status_code == 401


def test_admin_route_requires_token(client):
    response = client.get("/api/appointments")
    assert response.status_code == 401


def test_admin_route_rejects_patient_role(client):
    token = _register(client).json()["access_token"]
    response = client.get("/api/appointments", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_conversation_endpoint_requires_patient_token_before_touching_llm(client):
    """Sin token, debe fallar con 401 (auth) y no con 503 (LLM sin API key),
    lo que confirma que el guard de autenticacion corre antes de construir
    el cliente de OpenRouter."""
    response = client.post("/api/conversation/message", json={"message": "hola"})
    assert response.status_code == 401


def test_me_appointments_scoped_to_caller_only(client, db_session, doctor):
    token_a = _register(client, email="a@example.com", name="Paciente A").json()["access_token"]
    token_b = _register(client, email="b@example.com", name="Paciente B").json()["access_token"]

    patient_a = db_session.query(Patient).filter_by(email="a@example.com").one()
    patient_b = db_session.query(Patient).filter_by(email="b@example.com").one()

    db_session.add(
        Appointment(
            patient_id=patient_a.id,
            doctor_id=doctor.id,
            datetime_=dt.datetime.now() + dt.timedelta(days=1),
            status=AppointmentStatus.PENDIENTE,
        )
    )
    db_session.add(
        Appointment(
            patient_id=patient_b.id,
            doctor_id=doctor.id,
            datetime_=dt.datetime.now() + dt.timedelta(days=2),
            status=AppointmentStatus.PENDIENTE,
        )
    )
    db_session.commit()

    response = client.get("/api/me/appointments", headers={"Authorization": f"Bearer {token_a}"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["patient_id"] == patient_a.id
