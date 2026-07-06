"""Tests de ActionAI: que el listado de medicos llegue al prompt y que las
salidas invalidas degraden a Intent.NONE (fail closed)."""

from __future__ import annotations

import json

from app.ai.action_ai import ActionAI
from app.schemas.ai import Intent

from .fakes import FakeLLMClient


def test_extract_includes_doctors_roster_in_prompt():
    fake_llm = FakeLLMClient(json.dumps({"intent": "NONE", "patient_id": 1}))
    action_ai = ActionAI(fake_llm)

    action_ai.extract(
        history=[{"role": "user", "content": "hola"}],
        patient_id=1,
        doctors=[{"id": 7, "name": "Dra. Carmen Vega", "specialty": "Cardiología"}],
    )

    system_prompt = fake_llm.calls[0][0]["content"]
    assert "id=7" in system_prompt
    assert "Dra. Carmen Vega" in system_prompt
    assert "Cardiología" in system_prompt


def test_extract_without_doctors_still_works():
    fake_llm = FakeLLMClient(json.dumps({"intent": "NONE", "patient_id": 1}))
    action_ai = ActionAI(fake_llm)

    action = action_ai.extract(history=[{"role": "user", "content": "hola"}], patient_id=1)

    assert action.intent == Intent.NONE
    assert "no hay medicos registrados" in fake_llm.calls[0][0]["content"]


def test_extract_degrades_to_none_on_invalid_json():
    fake_llm = FakeLLMClient("esto no es json")
    action_ai = ActionAI(fake_llm)

    action = action_ai.extract(history=[{"role": "user", "content": "hola"}], patient_id=1)

    assert action.intent == Intent.NONE
    assert action.patient_id == 1
