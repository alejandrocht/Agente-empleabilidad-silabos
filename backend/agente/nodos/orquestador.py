"""Single orchestration operation used by the CIAR graph."""

from __future__ import annotations

import asyncio
import math
import os
import re
import unicodedata
from typing import Literal, Protocol, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from agente.utils.llm import ORCHESTRATOR_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_error, log_event
from agente.utils.prompt import build_orchestrator_user_prompt
from agente.utils.validacion import EntradaInvalida, validar_pregunta
from agente.utils.verbose import verbose_label, verbose_step

Route = Literal["conversacion", "cypher", "finalizar"]
ModelRoute = Literal["conversacion", "cypher"]

SAFE_ORCHESTRATOR_ERROR = (
    "No pude determinar de forma segura cómo procesar tu consulta. Intentá reformularla."
)
DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS = 30.0
_GRAPH_TERMS = frozenset(
    {
        "carrera", "carreras", "cargo", "cargos", "curso", "cursos",
        "coordinador", "coordinadores", "coordina", "coordinan",
        "docente", "docentes", "profesor", "profesora", "profesores",
        "profesoras", "ensena", "dicta", "dictan",
        "empresa", "empresas", "empleabilidad", "herramienta", "herramientas",
        "habilidad", "habilidades", "laboral", "laborales", "mercado",
        "oferta", "ofertas", "puesto", "puestos", "requerimiento",
        "requerimientos", "salario", "salarios", "silabo", "silabos",
        "trabajo", "trabajos", "vacante", "vacantes",
    }
)
_SCHEMA_REQUEST_TERMS = frozenset(
    {
        "que", "cual", "cuales", "cuanto", "cuantos", "cuantas", "quien",
        "donde", "como", "hay", "existe", "existen", "lista", "listar",
        "contar", "comparar", "relacionar", "ofrece", "publica", "requiere",
        "tiene", "coordina", "ensena", "dicta",
    }
)
_IDENTITY_TERMS = frozenset(
    {
        "coordinador", "coordinadores", "coordina", "coordinan", "docente",
        "docentes", "profesor", "profesora", "profesores", "profesoras",
    }
)
_ACADEMIC_ENTITY_TERMS = frozenset(
    {"carrera", "carreras", "curso", "cursos", "silabo", "silabos"}
)


class OrchestrationDecision(BaseModel):
    """Structured response returned by the orchestration model."""

    model_config = ConfigDict(extra="forbid")

    ruta: ModelRoute
    pregunta_mejorada: str = Field(min_length=1, max_length=500)


class OrchestratorRunnable(Protocol):
    """Minimal async interface used to inject a model in tests."""

    async def ainvoke(self, input: list[BaseMessage]) -> object: ...


async def orquestador(
    pregunta: str,
    prompt: str,
    *,
    orchestrator_runnable: OrchestratorRunnable | None = None,
) -> dict[str, str]:
    """Classify and conservatively correct one question in a single operation."""
    if not isinstance(pregunta, str) or not pregunta.strip() or not isinstance(prompt, str):
        return {
            "ruta": "finalizar",
            "respuesta": SAFE_ORCHESTRATOR_ERROR,
            "error": "orchestrator_failed",
        }

    try:
        pregunta = validar_pregunta(pregunta)
    except EntradaInvalida:
        return {
            "ruta": "finalizar",
            "respuesta": SAFE_ORCHESTRATOR_ERROR,
            "error": "orchestrator_failed",
        }

    user_prompt = build_orchestrator_user_prompt(pregunta)
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=user_prompt),
    ]
    verbose_step(
        "orquestador",
        "Entrada recibida",
        {"Pregunta": pregunta},
    )
    verbose_step(
        "orquestador",
        "Prompt enviado al modelo",
        {"Instrucciones": prompt, "Consulta": user_prompt},
    )

    raw_timeout = os.getenv("CIAR_ORCHESTRATOR_TIMEOUT_SECONDS", "30")
    try:
        timeout = float(raw_timeout)
    except ValueError:
        timeout = DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS
    if not math.isfinite(timeout) or timeout <= 0:
        timeout = DEFAULT_ORCHESTRATOR_TIMEOUT_SECONDS

    failure_reason: str | None = None
    try:
        runnable = orchestrator_runnable or cast(
            OrchestratorRunnable,
            build_chat_openai(ORCHESTRATOR_CHAT_PROFILE, constructor=ChatOpenAI)
            .with_structured_output(OrchestrationDecision, method="function_calling"),
        )
        raw_result = await asyncio.wait_for(
            runnable.ainvoke(messages),
            timeout=timeout,
        )
        decision = (
            raw_result
            if isinstance(raw_result, OrchestrationDecision)
            else OrchestrationDecision.model_validate(raw_result)
        )
        try:
            improved_question = validar_pregunta(decision.pregunta_mejorada)
        except EntradaInvalida as exc:
            raise ValueError("Orchestrator returned an unsafe improved question") from exc
        output: dict[str, str] = {
            "ruta": decision.ruta,
            "pregunta_mejorada": improved_question,
        }
        normalized = unicodedata.normalize("NFKD", improved_question.casefold())
        without_accents = "".join(
            character for character in normalized if not unicodedata.combining(character)
        )
        tokens = frozenset(re.findall(r"[a-z0-9]+", without_accents))
        schema_query_detected = bool(
            (tokens & _GRAPH_TERMS and tokens & _SCHEMA_REQUEST_TERMS)
            or (tokens & _IDENTITY_TERMS and tokens & _ACADEMIC_ENTITY_TERMS)
        )
        model_route = decision.ruta
        route = "cypher" if schema_query_detected else model_route
        output["ruta"] = route
        if route != model_route:
            log_event(
                "orchestrator",
                "route_corrected",
                model_route=model_route,
                route=route,
                reason="schema_query_detected",
                status="corrected",
            )
        question_improved = improved_question.strip() != pregunta.strip()
        verbose_step(
            "orquestador",
            "Respuesta del modelo",
            {
                "Ruta modelo": model_route,
                "Ruta final": route,
                "Pregunta mejorada": question_improved,
            },
        )
    except TimeoutError as exc:
        failure_reason = "timeout"
        log_error("orchestrator", failure_reason, exc)
    except Exception as exc:
        failure_reason = "failed"
        log_error("orchestrator", failure_reason, exc)

    if failure_reason is not None:
        normalized = unicodedata.normalize("NFKD", pregunta.casefold())
        without_accents = "".join(
            character for character in normalized if not unicodedata.combining(character)
        )
        tokens = frozenset(re.findall(r"[a-z0-9]+", without_accents))
        route = "cypher" if tokens & _GRAPH_TERMS else "conversacion"
        verbose_label("orquestador", "Resultado de respaldo", f"Ruta: {route}")
        log_event(
            "orchestrator",
            "degraded_route",
            route=route,
            reason=failure_reason,
            level="warning",
        )
        return {"ruta": route, "pregunta_mejorada": pregunta}

    log_event(
        "orchestrator",
        "route_selected",
        route=route,
        model_route=model_route,
        status="success",
        model_driven=True,
        route_corrected=route != model_route,
        question_improved=output["pregunta_mejorada"].strip() != pregunta.strip(),
    )
    verbose_label("orquestador", "Decisión final", f"Ruta: {route}")
    return output
