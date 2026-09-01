"""Generate and validate one bounded read-only Cypher query."""

from __future__ import annotations

import os
import re
import sys
import time
import unicodedata
from collections.abc import Mapping

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from agente.grafo.estado import Estado
from agente.nodos.generar_cypher import (
    GeneratedQuery,
    GeneratedQueryRunnable,
    SchemaValidationError,
    build_generated_query_runnable,
    correct_relationship_direction,
    summarize_schema,
    validate_generated_schema,
)
from agente.utils.cypher_guard import CypherGuardError, guard_cypher
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
_TEXT_SEARCH_PARAMETER_NAMES = frozenset(
    {"texto", "curso_texto", "herramienta_texto", "habilidad_texto", "competencia_texto"}
)
_GAP_DIMENSIONS = {
    "herramient": ("Herramienta", "ENSENIA"),
    "habilidad": ("Habilidad", "DESARROLLA"),
    "competenc": ("Competencia", "CUBRE"),
}
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


def _fold_search_text(value: str) -> str:
    """Fold case and accents only for structural intent checks."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _normalize_text_search_parameters(
    parameters: Mapping[str, object],
    question: object,
) -> dict[str, object]:
    del question
    return {
        name: (
            value.strip()
            if name in _TEXT_SEARCH_PARAMETER_NAMES and isinstance(value, str)
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


def _validate_follow_up_shape(cypher: str, question: object) -> None:
    if not isinstance(question, str):
        return
    folded_question = _fold_search_text(question)
    if not re.search(r"\bcon\s+que\s+(?:tecnologia|herramienta)", folded_question):
        return
    if not re.search(r":(?:Herramienta|Tecnologia)\b", cypher, re.IGNORECASE):
        raise SchemaValidationError(
            "Technology follow-up must traverse a Herramienta or Tecnologia node"
        )


def _gap_dimension(question: object) -> tuple[str, str] | None:
    """Return the requested curriculum/market dimension for an explicit gap question."""
    if not isinstance(question, str):
        return None
    folded = _fold_search_text(question)
    asks_for_absence = any(
        marker in folded
        for marker in (
            "brecha",
            "falta",
            "faltan",
            "no cubre",
            "no cubren",
            "no ensena",
            "no ensenan",
            "carece",
        )
    )
    mentions_market_demand = any(
        marker in folded
        for marker in (
            "mercado",
            "laboral",
            "oferta",
            "exige",
            "exigen",
            "pide",
            "piden",
            "requiere",
            "requieren",
            "solicita",
            "solicitan",
        )
    )
    if not asks_for_absence or not mentions_market_demand:
        return None
    return next(
        (contract for stem, contract in _GAP_DIMENSIONS.items() if stem in folded),
        None,
    )


def _validate_gap_shape(cypher: str, question: object) -> None:
    """Reject executable-looking anti-joins that do not actually filter covered items."""
    dimension = _gap_dimension(question)
    if dimension is None:
        return
    label, curriculum_relationship = dimension
    if re.search(r"(?i)\bOPTIONAL\s+MATCH\b", cypher):
        raise SchemaValidationError(
            f"Curriculum-market gap for {label} cannot use OPTIONAL MATCH"
        )

    demand = re.search(
        rf"(?i)\[\s*:\s*REQUIERE\s*\]\s*->\s*"
        rf"\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*{label}\b[^)]*\)",
        cypher,
    )
    career = re.search(
        r"(?i)\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*Carrera\b[^)]*\)",
        cypher,
    )
    if demand is None or career is None:
        raise SchemaValidationError(
            f"Curriculum-market gap for {label} must connect demand and curriculum"
        )

    dimension_variable = re.escape(demand.group("variable"))
    career_variable = re.escape(career.group("variable"))
    node = r"\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?(?::\s*{label}\s*)?\)"
    course_node = node.format(label="Curso")
    coverage_node = node.format(label="Cobertura_Curricular")
    negative_curriculum_pattern = re.compile(
        rf"(?is)\bNOT\s*\(\s*{career_variable}(?:\s*:\s*Carrera)?\s*\)\s*"
        rf"-\[\s*:\s*ENSENIA\s*\]->\s*{course_node}\s*"
        rf"-\[\s*:\s*TIENE\s*\]->\s*{coverage_node}\s*"
        rf"-\[\s*:\s*{curriculum_relationship}\s*\]->\s*"
        rf"\(\s*{dimension_variable}(?:\s*:\s*{label})?\s*\)"
    )
    negative_match = negative_curriculum_pattern.search(cypher)
    if negative_match is None:
        raise SchemaValidationError(
            f"Curriculum-market gap for {label} must use a NOT pattern over the same "
            "market-demand variable"
        )
    outside_negative_pattern = (
        cypher[: negative_match.start()] + cypher[negative_match.end() :]
    )
    if re.search(r"(?i):\s*Cobertura_Curricular\b", outside_negative_pattern):
        raise SchemaValidationError(
            f"Curriculum-market gap for {label} cannot require curriculum coverage "
            "outside the NOT pattern"
        )
    if re.search(r"(?i)\bTRUE\s+AS\s+brecha_curricular\b", cypher) is None:
        raise SchemaValidationError(
            f"Curriculum-market gap for {label} must project true AS brecha_curricular"
        )


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
                            estado.get("pregunta_contextualizada", estado["pregunta"]),
                            schema_summary,
                            corrective_feedback,
                        )
                    ),
                ]
                prompt_breakdown: dict[str, object] = {
                    "system_prompt": messages[0].content,
                    "question": estado.get("pregunta_contextualizada", estado["pregunta"]),
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
                        "parameters": _normalize_text_search_parameters(
                            generated.parameters,
                            estado.get("pregunta_contextualizada", estado["pregunta"]),
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
                _validate_follow_up_shape(
                    corrected_cypher,
                    estado.get("pregunta_contextualizada", estado["pregunta"]),
                )
                _validate_gap_shape(
                    corrected_cypher,
                    estado.get("pregunta_contextualizada", estado["pregunta"]),
                )
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
