"""Dobles de prueba (test doubles) para los componentes de IA.

Evita llamadas de red reales a OpenRouter en la suite de pytest: tanto
FrontDeskAI como ActionAI reciben el mismo LLMClient inyectado, asi que el
fake distingue cual de las dos IAs lo esta llamando mirando el system
prompt (cada una tiene un prompt claramente distinto).
"""

from __future__ import annotations

from app.ai.llm_client import LLMClient
from app.exceptions import LLMServiceError


class FakeLLMClient(LLMClient):
    def __init__(self, action_json: str, front_desk_text: str = "Listo, ¿en que más te ayudo?") -> None:
        self.action_json = action_json
        self.front_desk_text = front_desk_text
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages, model, max_tokens=600, response_format=None):
        self.calls.append(messages)
        system_content = messages[0]["content"]
        if "extractor de intenciones" in system_content:
            return self.action_json, 10
        return self.front_desk_text, 10


class FailingLLMClient(LLMClient):
    """Simula una caida del proveedor de LLM (timeout, 429, 5xx, etc.)."""

    def chat(self, messages, model, max_tokens=600, response_format=None):
        raise LLMServiceError("Servicio de IA no disponible (simulado para tests).")
