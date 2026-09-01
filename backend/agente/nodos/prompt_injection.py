"""Fail-closed input validation seam for graph requests."""

from __future__ import annotations

from typing import cast

from agente.grafo.estado import Estado
from agente.utils.logger import log_error, log_event
from agente.utils.validacion import EntradaInvalida, validar_pregunta
from agente.utils.verbose import verbose_step

SAFE_INPUT_ERROR = "No pude procesar tu consulta de forma segura. Reformulala e intenta nuevamente."


def prompt_injection(estado: Estado) -> Estado:
    """Validate the question before any schema, model, or database work."""
    return _validate_question_field(
        estado,
        field="pregunta",
        step="prompt_injection",
    )


def contextualized_prompt_injection(estado: Estado) -> Estado:
    """Revalidate the contextualized question before models or database access."""
    return _validate_question_field(
        estado,
        field="pregunta_contextualizada",
        step="contextualized_prompt_injection",
    )


def _validate_question_field(estado: Estado, *, field: str, step: str) -> Estado:
    if estado.get("error"):
        return {}

    pregunta = estado.get(field)
    length = len(pregunta) if isinstance(pregunta, str) else 0
    log_event(
        "prompt_injection",
        "validation_started",
        step=step,
        length=length,
    )
    try:
        validada = validar_pregunta(pregunta)
    except EntradaInvalida as exc:
        verbose_step("prompt_injection", "Entrada rechazada")
        log_error(
            "prompt_injection",
            "rejected",
            exc,
            step=step,
            reason=exc.tipo,
            status="failed",
            length=length,
        )
        return {
            "respuesta": SAFE_INPUT_ERROR,
            "filas": [],
            "error": "prompt_injection_failed",
        }

    log_event(
        "prompt_injection",
        "validated",
        step=step,
        status="success",
        length=len(validada),
    )
    verbose_step("prompt_injection", "Entrada validada")
    return cast(Estado, {field: validada, "error": None})
