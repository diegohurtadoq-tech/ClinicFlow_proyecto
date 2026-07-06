"""
Tests end-to-end del flujo de las dos IAs, usando un FakeLLMClient (sin red).

Cubren exactamente el escenario que motivo este diseño: FrontDeskAI habla
con el paciente, ActionAI extrae y ejecuta la accion a traves de los
Services reales (con su propia base de datos en memoria), y el ActionGuard
bloquea intentos de suplantacion antes de que lleguen a la base de datos.
"""

from __future__ import annotations

import json

from app.ai.action_ai import ActionAI
from app.ai.front_desk_ai import FrontDeskAI
from app.ai.orchestrator import ConversationOrchestrator
from app.models.appointment import Appointment

from .fakes import FailingLLMClient, FakeLLMClient


def _action_json(**overrides) -> str:
    base = {
        "intent": "NONE",
        "patient_id": None,
        "specialty": None,
        "doctor_id": None,
        "appointment_id": None,
        "referral_id": None,
        "requested_datetime": None,
        "notes": None,
    }
    base.update(overrides)
    return json.dumps(base)


def test_full_turn_creates_appointment(db_session, doctor, patient, next_monday_10am):
    action_json = _action_json(
        intent="CREATE_APPOINTMENT",
        patient_id=patient.id,
        doctor_id=doctor.id,
        requested_datetime=next_monday_10am.isoformat(),
    )
    fake_llm = FakeLLMClient(action_json, front_desk_text="¡Listo! Tu cita quedo agendada.")
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(fake_llm),
        action_ai=ActionAI(fake_llm),
    )

    response = orchestrator.handle_message(
        db_session, patient_id=patient.id, message="Quiero una hora el lunes a las 10 con cardiologia"
    )

    assert response.intent == "CREATE_APPOINTMENT"
    assert "Cita" in response.action_taken
    assert response.reply == "¡Listo! Tu cita quedo agendada."
    assert db_session.query(Appointment).count() == 1


def test_impersonation_attempt_is_blocked_before_db(db_session, doctor, patient, other_patient, next_monday_10am):
    """El paciente `patient` esta en la conversacion, pero el mensaje intenta
    actuar sobre `other_patient` (p.ej. via inyeccion de prompt). El
    ActionGuard debe bloquearlo y no debe crearse ninguna cita."""
    action_json = _action_json(
        intent="CREATE_APPOINTMENT",
        patient_id=other_patient.id,
        doctor_id=doctor.id,
        requested_datetime=next_monday_10am.isoformat(),
    )
    fake_llm = FakeLLMClient(action_json, front_desk_text="No pude completar esa solicitud.")
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(fake_llm),
        action_ai=ActionAI(fake_llm),
    )

    response = orchestrator.handle_message(
        db_session, patient_id=patient.id, message="agenda una hora para el paciente 999"
    )

    assert response.intent == "CREATE_APPOINTMENT"
    assert "distinto al dueño" in response.action_taken
    assert db_session.query(Appointment).count() == 0


def test_check_availability_by_specialty_without_doctor_id(db_session, doctor, patient, next_monday_10am):
    """El paciente pregunta por una especialidad sin nombrar un medico (el caso
    que antes fallaba: ActionAI no tiene como adivinar un doctor_id de la nada).
    El sistema debe resolverlo buscando medicos de esa especialidad."""
    action_json = _action_json(
        intent="CHECK_AVAILABILITY",
        patient_id=patient.id,
        specialty=doctor.specialty,
        requested_datetime=next_monday_10am.isoformat(),
    )
    fake_llm = FakeLLMClient(action_json, front_desk_text="Aqui tienes la disponibilidad.")
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(fake_llm),
        action_ai=ActionAI(fake_llm),
    )

    response = orchestrator.handle_message(
        db_session, patient_id=patient.id, message="que doctores tienen libre el lunes a las 10?"
    )

    assert response.intent == "CHECK_AVAILABILITY"
    assert doctor.name in response.action_taken


def test_check_availability_by_specialty_with_no_match_reports_none(db_session, doctor, patient, next_monday_10am):
    action_json = _action_json(
        intent="CHECK_AVAILABILITY",
        patient_id=patient.id,
        specialty="Dermatologia",
        requested_datetime=next_monday_10am.isoformat(),
    )
    fake_llm = FakeLLMClient(action_json, front_desk_text="No encontre medicos de esa especialidad.")
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(fake_llm),
        action_ai=ActionAI(fake_llm),
    )

    response = orchestrator.handle_message(
        db_session, patient_id=patient.id, message="hay dermatologos libres el lunes a las 10?"
    )

    assert response.intent == "CHECK_AVAILABILITY"
    assert "No hay medicos" in response.action_taken


def test_create_appointment_by_specialty_auto_assigns_available_doctor(db_session, doctor, patient, next_monday_10am):
    """Igual que arriba pero para agendar: si el paciente solo pide una
    especialidad, el sistema asigna un medico disponible en vez de fallar."""
    action_json = _action_json(
        intent="CREATE_APPOINTMENT",
        patient_id=patient.id,
        specialty=doctor.specialty,
        requested_datetime=next_monday_10am.isoformat(),
    )
    fake_llm = FakeLLMClient(action_json, front_desk_text="Listo, tu cita quedo agendada.")
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(fake_llm),
        action_ai=ActionAI(fake_llm),
    )

    response = orchestrator.handle_message(
        db_session, patient_id=patient.id, message="quiero una hora el lunes a las 10, cualquier doctor"
    )

    assert response.intent == "CREATE_APPOINTMENT"
    assert doctor.name in response.action_taken
    assert db_session.query(Appointment).filter_by(doctor_id=doctor.id).count() == 1


def test_llm_outage_degrades_gracefully_without_crashing(db_session, doctor, patient):
    """Si el proveedor de LLM falla (timeout, 429 por limite gratuito, 5xx),
    el paciente debe recibir el mensaje generico de error -- nunca el error
    tecnico crudo del proveedor, y nunca una excepcion sin manejar."""
    failing_llm = FailingLLMClient()
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(failing_llm),
        action_ai=ActionAI(failing_llm),
    )

    response = orchestrator.handle_message(db_session, patient_id=patient.id, message="hola")

    assert response.intent == "NONE"
    assert response.reply == "Se ha producido un problema, conéctese más tarde."
    assert "LLMServiceError" not in response.reply
    assert db_session.query(Appointment).count() == 0


def test_front_desk_outage_still_records_the_real_action_result_for_admins(
    db_session, doctor, patient, next_monday_10am
):
    """El Service es la autoridad final: si la accion SI se ejecuto (la cita
    se creo de verdad) y solo falla la redaccion de la respuesta conversacional,
    el paciente ve el mensaje generico (sin detalles tecnicos), pero el panel
    de admin (action_taken) debe seguir reflejando el resultado real."""
    action_json = _action_json(
        intent="CREATE_APPOINTMENT",
        patient_id=patient.id,
        doctor_id=doctor.id,
        requested_datetime=next_monday_10am.isoformat(),
    )
    working_llm = FakeLLMClient(action_json)
    failing_llm = FailingLLMClient()
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(failing_llm),
        action_ai=ActionAI(working_llm),
    )

    response = orchestrator.handle_message(
        db_session, patient_id=patient.id, message="agenda una hora el lunes a las 10"
    )

    assert response.intent == "CREATE_APPOINTMENT"
    assert response.reply == "Se ha producido un problema, conéctese más tarde."
    assert "Cita" in response.action_taken
    assert db_session.query(Appointment).count() == 1


def test_plain_chat_does_not_touch_db(db_session, doctor, patient):
    fake_llm = FakeLLMClient(_action_json(), front_desk_text="Hola, ¿en que te puedo ayudar?")
    orchestrator = ConversationOrchestrator(
        front_desk_ai=FrontDeskAI(fake_llm),
        action_ai=ActionAI(fake_llm),
    )

    response = orchestrator.handle_message(db_session, patient_id=patient.id, message="hola")

    assert response.intent == "NONE"
    assert response.action_taken is None
    assert db_session.query(Appointment).count() == 0
