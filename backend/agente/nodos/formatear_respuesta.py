"""Grounded answer formatter shared by all bounded graph-query routes."""

from __future__ import annotations

import json
from typing import Protocol, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agente.grafo.estado import Estado
from agente.utils.llm import GROUNDED_ANSWER_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_error, log_event
from agente.utils.prompt import build_grounded_answer_prompt
from agente.utils.response_text import normalize_response_text

NO_RESULTS_RESPONSE = (
    "No encontré datos relacionados dentro del alcance académico y de empleabilidad del agente "
    "CIAR. Prueba con carreras, cursos, facultades, empresas, ofertas, puestos, herramientas o "
    "competencias."
)
UNRESOLVED_ENTITY_RESPONSE = "No pude identificar una entidad única para esa consulta."
NO_CURRICULUM_RESPONSE = "No encontré currículo asociado a esa entidad."
SAFE_FORMATTER_FALLBACK = (
    "No pude redactar una respuesta segura con los resultados disponibles."
)


class GroundedAnswerRunnable(Protocol):
    """Minimal async runnable contract for injected Responses API models."""

    async def ainvoke(self, input: list[BaseMessage]) -> BaseMessage: ...


def build_grounded_answer_runnable() -> GroundedAnswerRunnable:
    """Create the formatter lazily and force the OpenAI Responses API."""
    log_event("answer_formatter", "model_configured", model_configured=True)
    return cast(
        GroundedAnswerRunnable,
        build_chat_openai(GROUNDED_ANSWER_CHAT_PROFILE, constructor=ChatOpenAI),
    )


def _build_grounded_input(estado: Estado) -> str:
    rows = json.dumps(
        estado.get("filas", []),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return (
        "Pregunta de la persona usuaria:\n"
        f"{estado['pregunta']}\n\n"
        "Filas verificadas de la base de datos:\n"
        f"{rows}"
    )


async def formatear_respuesta(
    estado: Estado,
    *,
    grounded_runnable: GroundedAnswerRunnable | None = None,
) -> Estado:
    """Render a public answer from only the question and bounded normalized rows."""
    prepared_response = estado.get("respuesta")
    if estado.get("curriculum_status") == "no_curriculum":
        log_event("answer_formatter", "no_curriculum", status="empty")
        return {"respuesta": NO_CURRICULUM_RESPONSE}
    if estado.get("entity_resolution") in {
        "failed",
        "unresolved",
        "ambiguous",
        "unsupported",
    } and not estado.get("error"):
        log_event("answer_formatter", "unresolved_entity", status="failed")
        return {"respuesta": UNRESOLVED_ENTITY_RESPONSE, "error": "entity_resolution_failed"}
    if estado.get("error"):
        log_event("answer_formatter", "skipped_after_failure", status="failed")
        return {
            "respuesta": prepared_response or SAFE_FORMATTER_FALLBACK,
            "error": estado["error"],
        }
    if isinstance(prepared_response, str) and prepared_response.strip():
        log_event("answer_formatter", "prepared_response_used")
        return {"respuesta": prepared_response}

    rows = estado.get("filas", [])
    if not rows:
        log_event("answer_formatter", "no_results", rows_count=0)
        return {"respuesta": NO_RESULTS_RESPONSE}

    log_event("answer_formatter", "started", rows_count=len(rows))
    messages = [
        SystemMessage(content=build_grounded_answer_prompt()),
        HumanMessage(content=_build_grounded_input(estado)),
    ]
    try:
        runnable = grounded_runnable or build_grounded_answer_runnable()
        result = await runnable.ainvoke(messages)
        answer = normalize_response_text(getattr(result, "content", None))
    except Exception as exc:
        log_error("answer_formatter", "failed", exc)
        return {"respuesta": SAFE_FORMATTER_FALLBACK, "error": "formatter_failed"}
    if not answer:
        log_event("answer_formatter", "empty_response", length=0, level="warning")
        return {"respuesta": SAFE_FORMATTER_FALLBACK, "error": "formatter_failed"}

    log_event("answer_formatter", "completed", length=len(answer))
    return {"respuesta": answer}
