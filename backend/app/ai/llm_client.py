"""
Cliente de LLM. `LLMClient` es la interfaz que usan FrontDeskAI y ActionAI;
`OpenRouterClient` es la implementacion real (mismo patron que el
ChatClient de Tarea 3: OpenRouter, API compatible con OpenAI).

Mantener esto detras de una interfaz permite inyectar un FakeLLMClient en
los tests, evitando llamadas de red reales (y costos) en la suite de pytest.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from ..config import get_settings
from ..exceptions import LLMServiceError

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.IGNORECASE | re.DOTALL)

# Patron para detectar razonamiento en texto plano sin etiquetas.
# Algunos modelos gratuitos emiten frases meta-analíticas en inglés antes
# de responder (ej: "We need to answer user, who wants...", "Let me think...",
# "The user is asking..."). Detectamos si el bloque empieza con esas frases
# y extraemos solo la ultima parte que parece dirigida al paciente.
_RAW_REASONING_PREFIXES = re.compile(
    r"^(We need to|Let me|I need to|The user (is asking|wants|said)|"
    r"Okay,? (so |let me|I need)|Alright,?|First,? I|Looking at|"
    r"Based on|The system|So,? (the|we|I)|Actually,|However,|But (we|I)|"
    r"Since (we|there|the)|Probably|Maybe (we|I)|It (says|seems|looks))",
    re.IGNORECASE,
)


def _strip_reasoning(content: str) -> str:
    """Limpia el razonamiento interno del modelo antes de devolver la respuesta.

    Estrategia en dos pasos:
    1. Eliminar bloques <think>...</think> explícitos.
    2. Si el texto resultante parece razonamiento en texto plano (inglés meta-
       analítico), intentar extraer solo el último párrafo en español.
    """
    # Paso 1: eliminar bloques <think>
    content = _THINK_BLOCK_RE.sub("", content).strip()

    # Paso 2: detectar razonamiento plano sin etiquetas.
    # Si el texto empieza con una frase típica de razonamiento interno,
    # buscamos el último párrafo que parezca la respuesta final al paciente.
    if _RAW_REASONING_PREFIXES.match(content):
        # Separar por doble salto de línea o por el último bloque significativo
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if p.strip()]
        if len(paragraphs) > 1:
            # El último párrafo generalmente es la respuesta final
            last = paragraphs[-1]
            # Solo usar si no empieza con razonamiento también
            if not _RAW_REASONING_PREFIXES.match(last):
                return last
        # Si todo es razonamiento, devolver vacío para triggear el fallback
        # del caller (FrontDeskAI devuelve mensaje genérico de error)
        return ""

    return content


class LLMClient(ABC):
    """Interfaz minima que necesitan FrontDeskAI y ActionAI."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int = 600,
        response_format: Optional[dict] = None,
    ) -> tuple[str, Optional[int]]:
        """Envia `messages` al modelo y retorna (texto_respuesta, tokens_usados).

        `response_format` (p.ej. {"type": "json_object"}) le pide al proveedor
        que devuelva unicamente un objeto JSON, sin texto/razonamiento alrededor.
        Lo usa ActionAI (salida estructurada); FrontDeskAI lo deja en None porque
        su respuesta es texto libre para el paciente."""
        ...


class OpenRouterClient(LLMClient):
    """Implementacion real sobre OpenRouter (API compatible con OpenAI)."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        self._api_key = (api_key or settings.openrouter_api_key).strip()
        if not self._api_key:
            raise LLMServiceError(
                "No se encontro la API key de OpenRouter. "
                "Define la variable de entorno OPENROUTER_API_KEY."
            )

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://clinicflow.local",
            "X-Title": "ClinicFlow AI Assistant",
        }

    _MAX_ATTEMPTS = 2

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int = 600,
        response_format: Optional[dict] = None,
    ) -> tuple[str, Optional[int]]:
        """Los modelos gratuitos de OpenRouter (p.ej. `openrouter/free`) a veces
        responden 200 OK con contenido vacio bajo carga/rate-limit. Un reintento
        unico resuelve la mayoria de esos casos sin enmascarar errores reales
        (HTTP/timeout siguen propagando LLMServiceError de inmediato)."""
        content, tokens = "", None
        for _attempt in range(self._MAX_ATTEMPTS):
            content, tokens = self._request(messages, model, max_tokens, response_format)
            if content.strip():
                break
        return content, tokens

    def _request(
        self,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        response_format: Optional[dict] = None,
    ) -> tuple[str, Optional[int]]:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            # Algunos modelos gratuitos enrutados por OpenRouter son modelos de
            # "razonamiento" (piensan paso a paso antes de responder). Este flag
            # unificado de OpenRouter les pide omitir ese rastro de la respuesta;
            # los modelos que no lo soportan simplemente lo ignoran.
            "reasoning": {"exclude": True},
        }
        if response_format is not None:
            payload["response_format"] = response_format
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    f"{OPENROUTER_BASE_URL}/chat/completions",
                    headers=self._build_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            raise LLMServiceError("Timeout al conectar con OpenRouter.") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMServiceError(
                f"HTTP {exc.response.status_code} desde OpenRouter: {exc.response.text[:200]}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMServiceError(f"Error de red: {exc}") from exc

        try:
            message = data["choices"][0]["message"]
            tokens = data.get("usage", {}).get("total_tokens")
        except (KeyError, IndexError) as exc:
            raise LLMServiceError(f"Respuesta inesperada de OpenRouter: {data}") from exc

        content = _strip_reasoning(message.get("content") or "")
        return content, tokens
