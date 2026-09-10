"""Generate and validate one bounded read-only Cypher query."""

from __future__ import annotations

import os
import re
import sys
import time
from collections.abc import Mapping

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from agente.grafo.estado import Estado, pregunta_para_procesar
from agente.nodos.contrato_cypher import (
    GeneratedQuery,
    GeneratedQueryRunnable,
    SchemaValidationError,
    build_generated_query_runnable,
    correct_relationship_direction,
    summarize_schema,
    validate_generated_schema,
)
from agente.utils.cypher_guard import CypherGuardError, guard_cypher
from agente.utils.db import query_fingerprint
from agente.utils.logger import (
    attempt_context,
    log_error,
    log_event,
)
from agente.utils.prompt import (
    build_cypher_correction_prompt,
    build_cypher_system_prompt,
    build_cypher_user_prompt,
)
from agente.utils.verbose import verbose_label, verbose_step

MAX_GENERATION_ATTEMPTS = 2
SAFE_GENERATION_ERROR = (
    "No pude consultar la información de forma segura en este momento. "
    "Intentá nuevamente más tarde."
)


def _redact_quoted_literals(cypher: str) -> str:
    """Keep Cypher structure while removing every quoted value or identifier."""
    redacted: list[str] = []
    index = 0
    while index < len(cypher):
        delimiter = cypher[index]
        if delimiter not in {"'", '"', "`"}:
            redacted.append(delimiter)
            index += 1
            continue

        redacted.append("<REDACTED>")
        index += 1
        while index < len(cypher):
            if delimiter != "`" and cypher[index] == "\\":
                index += 2
                continue
            if cypher[index] == delimiter:
                if index + 1 < len(cypher) and cypher[index + 1] == delimiter:
                    index += 2
                    continue
                index += 1
                break
            index += 1
    return "".join(redacted)


def _normalize_string_parameters(
    parameters: Mapping[str, object],
) -> dict[str, object]:
    return {
        name: (
            value.strip()
            if isinstance(value, str)
            else value
        )
        for name, value in parameters.items()
    }


def _debug_cypher(
    stage: str,
    cypher: str,
    parameters: Mapping[str, object] | None = None,
) -> None:
    """Emit temporary, redacted Cypher diagnostics only when explicitly enabled."""
    if os.getenv("CIAR_DEBUG_CYPHER") != "1":
        return

    parameter_metadata = "none"
    if parameters:
        parameter_metadata = ",".join(
            f"{name}:{type(value).__name__}" for name, value in sorted(parameters.items())
        )
    message = (
        f"[DEBUG-CYPHER] stage={stage} query_length={len(cypher)} "
        f"parameters={parameter_metadata}\n"
    )
    sys.stderr.write(message)
    sys.stderr.flush()


def _query_log_context(cypher: str, parameters: Mapping[str, object]) -> dict[str, object]:
    """Expose query shape and parameter names without parameter values."""
    return {
        "query_fingerprint": query_fingerprint(cypher),
        "query_structure": _redact_quoted_literals(cypher),
        "query_length": len(cypher),
        "parameter_names": sorted(parameters),
        "parameter_count": len(parameters),
    }


def _is_retryable(exc: Exception) -> bool:
    return not isinstance(exc, (PermissionError, SystemExit, KeyboardInterrupt))


def _reject_interpolated_values(cypher: str) -> None:
    """Require generated user values to travel through parameters, not literals."""
    if re.search(r"['\"`]", cypher):
        raise CypherGuardError("Generated Cypher must parameterize string values")


async def construye_cypher(
    estado: Estado,
    *,
    generated_runnable: GeneratedQueryRunnable | None = None,
    max_generation_attempts: int = MAX_GENERATION_ATTEMPTS,
) -> Estado:
    """Generate and statically validate Cypher using only the question and schema."""
    if estado.get("error"):
        return {}

    snapshot = estado.get("schema")
    if snapshot is None:
        return {"respuesta": SAFE_GENERATION_ERROR, "filas": [], "error": "schema_missing"}
    if max_generation_attempts < 1:
        raise ValueError("max_generation_attempts must be positive")

    attempts_allowed = min(max_generation_attempts, MAX_GENERATION_ATTEMPTS)
    question = pregunta_para_procesar(estado)
    if question is None:
        return {"respuesta": SAFE_GENERATION_ERROR, "filas": [], "error": "question_missing"}
    schema_summary = summarize_schema(snapshot.structured)
    runnable = generated_runnable
    corrective_feedback: str | None = None

    verbose_step(
        "construye_cypher",
        "Resumen de schema enviado al generador",
        f"schema_size={len(schema_summary)}",
    )

    for attempt in range(1, attempts_allowed + 1):
        with attempt_context(attempt):
            attempt_started_at = time.perf_counter()
            log_event(
                "dynamic_query",
                "attempt_started",
                attempt=attempt,
                stage="dynamic_generation",
                input_keys=["pregunta", "schema"],
            )
            try:
                if runnable is None:
                    runnable = build_generated_query_runnable()
                messages = [
                    SystemMessage(content=build_cypher_system_prompt()),
                    HumanMessage(
                        content=build_cypher_user_prompt(
                            question,
                            schema_summary,
                            corrective_feedback,
                        )
                    ),
                ]
                prompt_breakdown: dict[str, object] = {
                    "system_prompt": messages[0].content,
                    "question": question,
                    "schema_summary": schema_summary,
                }
                if corrective_feedback is not None:
                    prompt_breakdown["corrective_feedback"] = corrective_feedback
                verbose_step(
                    "construye_cypher",
                    f"Prompt enviado al generador (intento {attempt})",
                    f"input_keys={','.join(sorted(prompt_breakdown))}",
                )
                human_prompt = str(messages[1].content)
                request_context: dict[str, object] = {
                    "attempt": attempt,
                    "stage": "dynamic_generation",
                    "input_keys": ["system_prompt", "human_prompt"],
                    "input_size": len(messages[0].content) + len(human_prompt),
                    "prompt_size": len(human_prompt),
                }
                log_event("dynamic_query", "llm_request", context=request_context)
                generation_started_at = time.perf_counter()
                generated = GeneratedQuery.model_validate(await runnable.ainvoke(messages))
                generated = generated.model_copy(
                    update={
                        "parameters": _normalize_string_parameters(
                            generated.parameters,
                        )
                    }
                )
                generation_duration_ms = round(
                    (time.perf_counter() - generation_started_at) * 1000, 2
                )
                verbose_label("construye_cypher", "Longitud de Cypher", len(generated.cypher))
                verbose_label(
                    "construye_cypher",
                    "Nombres de parámetros",
                    sorted(generated.parameters),
                )
                verbose_step(
                    "construye_cypher",
                    "Respuesta recibida del generador",
                    duration_ms=generation_duration_ms,
                )
                log_event(
                    "dynamic_query",
                    "llm_response",
                    attempt=attempt,
                    status="structured",
                    duration_ms=generation_duration_ms,
                    output_keys=["cypher", "parameters"],
                    output_size=len(generated.cypher),
                    response_size=len(generated.cypher),
                    context=_query_log_context(generated.cypher, generated.parameters),
                )
                _debug_cypher("reject_interpolated_values", generated.cypher, generated.parameters)
                _reject_interpolated_values(generated.cypher)
                corrected_cypher = correct_relationship_direction(
                    generated.cypher, snapshot.structured, generated.parameters
                )
                _debug_cypher(
                    "validate_generated_schema", corrected_cypher, generated.parameters
                )
                log_event(
                    "dynamic_query",
                    "validation_started",
                    attempt=attempt,
                    stage="dynamic_generation",
                    context=_query_log_context(corrected_cypher, generated.parameters),
                )
                validate_generated_schema(corrected_cypher, snapshot.structured)
                _debug_cypher("guard_cypher", corrected_cypher, generated.parameters)
                guarded = guard_cypher(corrected_cypher, generated.parameters)
                log_event(
                    "dynamic_query",
                    "guard_accepted",
                    attempt=attempt,
                    status="success",
                    guard_decision="accepted",
                    read_only=True,
                    query_limit=guarded.limit,
                    context=_query_log_context(guarded.text, guarded.parameters),
                )
            except (ValidationError, SchemaValidationError, CypherGuardError) as exc:
                corrective_feedback = build_cypher_correction_prompt(exc)
                verbose_step(
                    "construye_cypher",
                    f"Validación rechazada en intento {attempt}",
                    str(exc),
                    duration_ms=round((time.perf_counter() - attempt_started_at) * 1000, 2),
                )
                log_error(
                    "dynamic_query",
                    "validation_failed",
                    exc,
                    attempt=attempt,
                    status="failed",
                    guard_decision="rejected",
                    duration_ms=round((time.perf_counter() - attempt_started_at) * 1000, 2),
                )
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                corrective_feedback = build_cypher_correction_prompt(exc)
                verbose_step(
                    "construye_cypher",
                    f"Generación falló en intento {attempt}",
                    str(exc),
                    duration_ms=round((time.perf_counter() - attempt_started_at) * 1000, 2),
                )
                log_error(
                    "dynamic_query",
                    "generation_failed",
                    exc,
                    attempt=attempt,
                    status="failed",
                    duration_ms=round((time.perf_counter() - attempt_started_at) * 1000, 2),
                )
            else:
                attempt_duration_ms = round(
                    (time.perf_counter() - attempt_started_at) * 1000, 2
                )
                verbose_label(
                    "construye_cypher", "Longitud de Cypher aceptado", len(guarded.text)
                )
                verbose_label(
                    "construye_cypher",
                    "Nombres de parámetros aceptados",
                    sorted(guarded.parameters),
                )
                verbose_label("construye_cypher", "Límite aplicado", guarded.limit)
                verbose_step(
                    "construye_cypher",
                    f"Cypher validado y listo para ejecutar (intento {attempt})",
                    duration_ms=attempt_duration_ms,
                )
                log_event(
                    "dynamic_query",
                    "validated",
                    attempt=attempt,
                    status="success",
                    length=len(guarded.text),
                    duration_ms=attempt_duration_ms,
                    context=_query_log_context(guarded.text, guarded.parameters),
                )
                return {
                    "cypher": guarded.text,
                    "parameters": guarded.parameters,
                    "query_limit": guarded.limit,
                }

    return {
        "respuesta": SAFE_GENERATION_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
