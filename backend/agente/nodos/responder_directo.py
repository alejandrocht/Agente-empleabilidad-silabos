"""Nodo asíncrono para respuestas que no requieren datos del grafo."""

from __future__ import annotations

import asyncio
import math
import os
from typing import Protocol, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agente.grafo.estado import Estado
from agente.utils.llm import ANALYST_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_error, log_event
from agente.utils.prompt import build_direct_response_prompt, build_direct_user_prompt
from agente.utils.response_text import normalize_response_text

SAFE_RESPONSE_FALLBACK = (
    "No pude generar una respuesta segura en este momento. Intentá reformular tu consulta."
)
DEFAULT_DIRECT_RESPONSE_TIMEOUT_SECONDS = 30.0


def _direct_response_timeout_seconds() -> float:
    """Return a positive conversational deadline without trusting bad config."""
    raw_value = os.getenv("CIAR_DIRECT_RESPONSE_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_DIRECT_RESPONSE_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_DIRECT_RESPONSE_TIMEOUT_SECONDS
    return value if math.isfinite(value) and value > 0 else DEFAULT_DIRECT_RESPONSE_TIMEOUT_SECONDS


class DirectResponseRunnable(Protocol):
    """Interfaz async mínima para inyectar un modelo sin red en pruebas."""

    async def ainvoke(self, input: list[BaseMessage]) -> BaseMessage: ...


def build_direct_response_runnable() -> DirectResponseRunnable:
    """Construye el modelo bajo demanda, sin herramientas ni efectos al importar."""
    log_event("direct_response", "model_configured", model_configured=True)
    return cast(
        DirectResponseRunnable,
        build_chat_openai(ANALYST_CHAT_PROFILE, constructor=ChatOpenAI),
    )


async def responder_directo(
    estado: Estado,
    *,
    direct_runnable: DirectResponseRunnable | None = None,
) -> Estado:
    """Genera solo la respuesta pública sin consultar recursos del dominio."""
    log_event("direct_response", "started")
    mensajes = [
        SystemMessage(content=build_direct_response_prompt()),
        HumanMessage(content=build_direct_user_prompt(estado["pregunta"])),
    ]
    try:
        runnable = direct_runnable or build_direct_response_runnable()
        result = await asyncio.wait_for(
            runnable.ainvoke(mensajes),
            timeout=_direct_response_timeout_seconds(),
        )
        answer = normalize_response_text(getattr(result, "content", None))
    except TimeoutError as exc:
        log_error("direct_response", "timeout", exc)
        return {"respuesta": SAFE_RESPONSE_FALLBACK, "error": "direct_response_timeout"}
    except Exception as exc:
        log_error("direct_response", "failed", exc)
        return {"respuesta": SAFE_RESPONSE_FALLBACK, "error": "direct_response_failed"}
    if not answer:
        log_event("direct_response", "empty_response", length=0, level="warning")
        return {"respuesta": SAFE_RESPONSE_FALLBACK, "error": "direct_response_failed"}

    log_event("direct_response", "completed", length=len(answer))
    return {"respuesta": answer}
