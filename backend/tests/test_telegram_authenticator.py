"""
Tests unitarios para PatientAuthenticator (almacenamiento en BD).
"""

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import ClinicFlowError
from app.models.telegram_link import TelegramLinkCode
from app.models.user import Patient
from app.telegram.authenticator import PatientAuthenticator


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Limpia el estado de rate limiting entre tests."""
    from app.telegram import authenticator as auth_module
    auth_module._link_attempts.clear()
    yield
    auth_module._link_attempts.clear()


@pytest.fixture
def authenticator():
    return PatientAuthenticator()


@pytest.fixture
def mock_db():
    db = MagicMock()
    # scalars().first() devuelve None por defecto (sin colisiones de codigo)
    db.scalars.return_value.first.return_value = None
    db.execute.return_value = None
    return db


# ─── generate_link_code ───────────────────────────────────────────────────────

def test_generate_link_code_format(authenticator, mock_db):
    """El codigo generado debe tener 8 caracteres alfanumericos en mayusculas."""
    patient = Patient(id=1, name="Juan Perez", email="juan@example.com", role="patient")
    mock_db.get.return_value = patient

    code = authenticator.generate_link_code(mock_db, patient_id=1)

    assert len(code) == 8
    assert code == code.upper()
    assert code.isalnum()


def test_generate_link_code_no_ambiguous_chars(authenticator, mock_db):
    """El codigo no debe contener O, 0, I ni 1 (caracteres ambiguos)."""
    patient = Patient(id=1, name="Juan Perez", email="juan@example.com", role="patient")
    mock_db.get.return_value = patient

    for _ in range(30):
        code = authenticator.generate_link_code(mock_db, patient_id=1)
        assert "O" not in code
        assert "0" not in code
        assert "I" not in code
        assert "1" not in code


def test_generate_link_code_patient_not_found(authenticator, mock_db):
    """Debe lanzar ClinicFlowError si el paciente no existe."""
    mock_db.get.return_value = None

    with pytest.raises(ClinicFlowError, match="Paciente 999 no encontrado"):
        authenticator.generate_link_code(mock_db, patient_id=999)


# ─── link_telegram_account ────────────────────────────────────────────────────

def test_link_telegram_account_success(authenticator, mock_db):
    """Vinculacion exitosa: retorna True y actualiza telegram_id del paciente."""
    patient = Patient(id=1, name="Juan Perez", email="juan@example.com", role="patient")
    expires = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=5)
    record = TelegramLinkCode(code="ABCD1234", patient_id=1, expires_at=expires, used=False)

    # Primera llamada a scalars: busca el codigo → devuelve record
    # Segunda llamada a scalars: verifica telegram_id duplicado → devuelve None
    mock_db.scalars.return_value.first.side_effect = [record, None]
    mock_db.get.return_value = patient

    success, message, patient_id = authenticator.link_telegram_account(
        mock_db, telegram_id="123456", link_code="ABCD1234"
    )

    assert success is True
    assert patient_id == 1
    assert "Juan Perez" in message
    assert patient.telegram_id == "123456"
    mock_db.commit.assert_called()


def test_link_telegram_account_normalizes_code(authenticator, mock_db):
    """El codigo debe normalizarse con strip+upper antes de buscar en BD."""
    patient = Patient(id=1, name="Ana Lopez", email="ana@example.com", role="patient")
    expires = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=5)
    record = TelegramLinkCode(code="ABCD1234", patient_id=1, expires_at=expires, used=False)

    mock_db.scalars.return_value.first.side_effect = [record, None]
    mock_db.get.return_value = patient

    # Codigo enviado en minusculas y con espacio
    success, _, _ = authenticator.link_telegram_account(
        mock_db, telegram_id="999", link_code="  abcd1234  "
    )
    assert success is True


def test_link_telegram_account_invalid_code(authenticator, mock_db):
    """Codigo no encontrado en BD debe retornar False."""
    mock_db.scalars.return_value.first.return_value = None

    success, message, patient_id = authenticator.link_telegram_account(
        mock_db, telegram_id="123456", link_code="INVALID1"
    )

    assert success is False
    assert patient_id is None
    assert "invalido o expirado" in message


def test_link_telegram_account_expired_code(authenticator, mock_db):
    """Codigo con expires_at en el pasado debe rechazarse."""
    expires = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(minutes=1)  # ya vencio
    record = TelegramLinkCode(code="EXPIRED1", patient_id=1, expires_at=expires, used=False)
    mock_db.scalars.return_value.first.return_value = record

    success, message, patient_id = authenticator.link_telegram_account(
        mock_db, telegram_id="123456", link_code="EXPIRED1"
    )

    assert success is False
    assert patient_id is None
    assert "expirado" in message
    mock_db.delete.assert_called_once_with(record)


def test_link_telegram_account_already_linked(authenticator, mock_db):
    """telegram_id ya vinculado a otro paciente debe rechazarse."""
    expires = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) + dt.timedelta(minutes=5)
    record = TelegramLinkCode(code="ABCD1234", patient_id=1, expires_at=expires, used=False)
    existing = Patient(id=2, name="Otro Paciente", email="otro@example.com",
                       role="patient", telegram_id="123456")

    # Primera llamada: busca codigo → record
    # Segunda llamada: busca telegram_id duplicado → existing
    mock_db.scalars.return_value.first.side_effect = [record, existing]

    success, message, patient_id = authenticator.link_telegram_account(
        mock_db, telegram_id="123456", link_code="ABCD1234"
    )

    assert success is False
    assert patient_id is None
    assert "ya esta vinculada" in message


def test_link_telegram_account_rate_limiting(authenticator, mock_db):
    """Debe rechazar tras 5 intentos fallidos en la ventana de tiempo."""
    mock_db.scalars.return_value.first.return_value = None  # codigo siempre invalido
    telegram_id = "ratelimit_test"

    # 5 intentos fallidos
    for _ in range(5):
        authenticator.link_telegram_account(mock_db, telegram_id=telegram_id, link_code="FAKE0001")

    # El 6to debe ser bloqueado por rate limiting antes de tocar la BD
    success, message, _ = authenticator.link_telegram_account(
        mock_db, telegram_id=telegram_id, link_code="FAKE0002"
    )
    assert success is False
    assert "Demasiados intentos" in message


# ─── get_patient_id / is_linked ───────────────────────────────────────────────

def test_get_patient_id_linked(authenticator, mock_db):
    patient = Patient(id=5, name="Carlos", email="c@c.cl", role="patient", telegram_id="789")
    mock_db.scalars.return_value.first.return_value = patient

    assert authenticator.get_patient_id(mock_db, "789") == 5


def test_get_patient_id_not_linked(authenticator, mock_db):
    mock_db.scalars.return_value.first.return_value = None

    assert authenticator.get_patient_id(mock_db, "999") is None


def test_is_linked_true(authenticator, mock_db):
    patient = Patient(id=1, name="X", email="x@x.cl", role="patient", telegram_id="111")
    mock_db.scalars.return_value.first.return_value = patient
    assert authenticator.is_linked(mock_db, "111") is True


def test_is_linked_false(authenticator, mock_db):
    mock_db.scalars.return_value.first.return_value = None
    assert authenticator.is_linked(mock_db, "000") is False
