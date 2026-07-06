"""Tests del saneamiento de salida de OpenRouterClient.

No se prueba la llamada de red real (eso requeriria mockear httpx, y el
resto de la suite deliberadamente evita tocar esa frontera: FrontDeskAI y
ActionAI siempre se prueban contra el LLMClient inyectado). Lo que si es
logica propia y vale la pena fijar con un test es `_strip_reasoning`: los
modelos gratuitos de OpenRouter (estilo DeepSeek-R1) a veces devuelven su
razonamiento interno envuelto en <think>...</think> antes de la respuesta
real, y eso nunca debe llegarle al paciente.
"""

from __future__ import annotations

from app.ai.llm_client import _strip_reasoning


def test_strip_reasoning_removes_think_block():
    raw = "<think>el paciente quiere agendar, reviso la especialidad...</think>¡Hola! ¿En que te ayudo?"
    assert _strip_reasoning(raw) == "¡Hola! ¿En que te ayudo?"


def test_strip_reasoning_is_case_insensitive_and_multiline():
    raw = "<THINK>\nlinea 1\nlinea 2\n</THINK>\nRespuesta final."
    assert _strip_reasoning(raw) == "Respuesta final."


def test_strip_reasoning_leaves_normal_text_untouched():
    raw = "Tu cita quedo agendada para el lunes a las 10:00."
    assert _strip_reasoning(raw) == raw
