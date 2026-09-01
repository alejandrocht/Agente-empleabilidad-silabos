"""LLM-based routing before schema, Cypher generation, or database access."""

from __future__ import annotations

import asyncio
import math
import os
import re
import unicodedata
from collections.abc import Mapping
from typing import Literal, Protocol, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict

from agente.grafo.estado import Estado
from agente.utils.llm import ORCHESTRATOR_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_error, log_event
from agente.utils.prompt import (
    build_orchestrator_system_prompt,
    build_orchestrator_user_prompt,
)

Route = Literal["conversacion", "cypher", "finalizar"]
ModelRoute = Literal["conversacion", "cypher"]

SAFE_ORCHESTRATOR_ERROR = (
    "No pude determinar de forma segura cómo procesar tu consulta. Intentá reformularla."
)
DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS = 30.0
_GRAPH_TERMS = frozenset(
    {
        "carrera", "carreras", "cargo", "cargos", "curso", "cursos",
        "empresa", "empresas", "empleabilidad", "herramienta", "herramientas",
        "habilidad", "habilidades", "laboral", "laborales", "mercado",
        "oferta", "ofertas", "puesto", "puestos", "requerimiento",
        "requerimientos", "salario", "salarios", "silabo", "silabos",
        "trabajo", "trabajos", "vacante", "vacantes",
    }
)


class OrchestrationDecision(BaseModel):
    """Validated output exposed by the orchestration model."""

    model_config = ConfigDict(extra="forbid")

    ruta: ModelRoute


class OrchestratorRunnable(Protocol):
    """Minimal async interface used to inject a network-free router in tests."""

    async def ainvoke(self, input: list[BaseMessage]) -> object: ...


def _orchestrator_timeout_seconds() -> float:
    raw_value = os.getenv("CIAR_ORCHESTRATOR_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS
    return value if math.isfinite(value) and value > 0 else DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS


def build_orchestrator_runnable() -> OrchestratorRunnable:
    """Build the routing model with a closed structured-output contract."""
    model = build_chat_openai(ORCHESTRATOR_CHAT_PROFILE, constructor=ChatOpenAI)
    return cast(
        OrchestratorRunnable,
        model.with_structured_output(OrchestrationDecision, method="function_calling"),
    )


def _route_from_result(result: object) -> ModelRoute:
    if isinstance(result, OrchestrationDecision):
        return result.ruta
    if isinstance(result, Mapping):
        return OrchestrationDecision.model_validate(result).ruta
    raise TypeError("Orchestrator returned an invalid structured decision")


def _degraded_route(question: str) -> ModelRoute:
    """Keep graph-shaped questions on the safe read-only path if routing fails."""
    normalized = unicodedata.normalize("NFKD", question.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    tokens = frozenset(re.findall(r"[a-z0-9]+", without_accents))
    return "cypher" if tokens & _GRAPH_TERMS else "conversacion"


async def orquestador(
    estado: Estado,
    *,
    orchestrator_runnable: OrchestratorRunnable | None = None,
) -> Estado:
    """Ask the orchestration model whether the request needs graph data."""
    if estado.get("error"):
        return {"ruta": "finalizar"}

    question = estado.get("pregunta_contextualizada") or estado.get("pregunta")
    if not isinstance(question, str) or not question.strip():
        return {
            "ruta": "finalizar",
            "respuesta": SAFE_ORCHESTRATOR_ERROR,
            "error": "orchestrator_failed",
        }

    messages = [
        SystemMessage(content=build_orchestrator_system_prompt()),
        HumanMessage(content=build_orchestrator_user_prompt(question)),
    ]
    try:
        runnable = orchestrator_runnable or build_orchestrator_runnable()
        result = await asyncio.wait_for(
            runnable.ainvoke(messages),
            timeout=_orchestrator_timeout_seconds(),
        )
        route = _route_from_result(result)
    except TimeoutError as exc:
        log_error("orchestrator", "timeout", exc)
        route = _degraded_route(question)
        log_event("orchestrator", "degraded_route", route=route, reason="timeout", level="warning")
        return {"ruta": route}
    except Exception as exc:
        log_error("orchestrator", "failed", exc)
        route = _degraded_route(question)
        log_event("orchestrator", "degraded_route", route=route, reason="failed", level="warning")
        return {"ruta": route}

    log_event("orchestrator", "route_selected", route=route, model_driven=True)
    return {"ruta": route}
