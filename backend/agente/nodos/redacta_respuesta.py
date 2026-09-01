"""Generate a bounded answer grounded in verified Neo4j rows."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from collections.abc import Mapping
from typing import Any, Protocol, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from agente.grafo.estado import Estado
from agente.utils.identifier_intent import requests_identifier
from agente.utils.llm import ANALYST_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_error, log_event
from agente.utils.prompt import (
    build_grounded_analysis_prompt,
    build_grounded_analysis_user_prompt,
)
from agente.utils.response_inspector import inspect_response

MAX_VISIBLE_ROWS = 20
MAX_VISIBLE_ITEMS = 20
MAX_FIELD_CHARS = 200
MAX_ANALYST_PAYLOAD_CHARS = 16_000
DEFAULT_ANALYST_TIMEOUT_SECONDS = 30.0
_NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?%?")
_NAMED_TOKEN = re.compile(r"\b[A-ZÁÉÍÓÚÜÑ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9_-]+\b")
_SAFE_SENTENCE_TOKENS = frozenset(
    {
        "datos",
        "el",
        "ella",
        "en",
        "esta",
        "estas",
        "este",
        "estos",
        "hay",
        "la",
        "las",
        "los",
        "no",
        "se",
        "son",
        "un",
        "una",
    }
)


class GroundedAnalysis(BaseModel):
    """One interpretive answer with the rows used as its evidence."""

    model_config = ConfigDict(extra="forbid")

    respuesta: str = Field(
        min_length=1,
        max_length=2_000,
        description="Respuesta final natural en español, basada únicamente en las filas.",
    )
    row_indices: list[int] = Field(
        min_length=1,
        max_length=MAX_VISIBLE_ROWS,
        description="Índices base cero de las filas que respaldan la respuesta.",
    )


class AnalystRunnable(Protocol):
    """Minimal async interface for the structured answer model."""

    async def ainvoke(self, input: list[BaseMessage]) -> object: ...


def build_analyst_runnable() -> AnalystRunnable:
    """Build the analyst with one answer and a set of evidence row references."""
    model = build_chat_openai(ANALYST_CHAT_PROFILE, constructor=ChatOpenAI)
    return cast(
        AnalystRunnable,
        model.with_structured_output(GroundedAnalysis, method="function_calling"),
    )


def _analyst_timeout_seconds() -> float:
    raw_value = os.getenv("CIAR_ANALYST_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_ANALYST_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_ANALYST_TIMEOUT_SECONDS
    return value if math.isfinite(value) and value > 0 else DEFAULT_ANALYST_TIMEOUT_SECONDS


def _is_identifier(key: str) -> bool:
    normalized = key.strip().casefold()
    return (
        normalized in {"id", "identificador"}
        or normalized.startswith("id_")
        or normalized.endswith("_id")
        or normalized.endswith("_ids")
    )


def _public_value(value: object, *, include_identifiers: bool) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, str):
        value = value.strip()
        return value if len(value) <= MAX_FIELD_CHARS else f"{value[:199].rstrip()}…"
    if isinstance(value, (list, tuple)):
        return [
            _public_value(item, include_identifiers=include_identifiers)
            for item in value[:MAX_VISIBLE_ITEMS]
        ]
    if isinstance(value, Mapping):
        return {
            str(key): _public_value(item, include_identifiers=include_identifiers)
            for key, item in list(value.items())[:MAX_VISIBLE_ITEMS]
            if isinstance(key, str) and (include_identifiers or not _is_identifier(key))
        }
    rendered = str(value)
    return rendered if len(rendered) <= MAX_FIELD_CHARS else f"{rendered[:199].rstrip()}…"


def _public_rows(rows: list[dict[str, Any]], question: str) -> list[dict[str, object]]:
    include_identifiers = requests_identifier(question)
    public_rows = [
        {
            key: _public_value(value, include_identifiers=include_identifiers)
            for key, value in row.items()
            if include_identifiers or not _is_identifier(key)
        }
        for row in rows[:MAX_VISIBLE_ROWS]
    ]
    bounded: list[dict[str, object]] = []
    for row in public_rows:
        if not row:
            continue
        candidate = [*bounded, row]
        payload_length = len(
            json.dumps(candidate, ensure_ascii=False, allow_nan=False)
        )
        if payload_length > MAX_ANALYST_PAYLOAD_CHARS:
            break
        bounded.append(row)
    return bounded


def _scalar_strings(value: object) -> set[str]:
    if isinstance(value, str) and len(value.strip()) >= 3:
        return {value.strip().casefold()}
    if isinstance(value, list):
        strings: set[str] = set()
        for item in value:
            strings.update(_scalar_strings(item))
        return strings
    if isinstance(value, Mapping):
        strings = set()
        for item in value.values():
            strings.update(_scalar_strings(item))
        return strings
    return set()


def _answer_is_grounded(
    answer: str,
    row_indices: list[int],
    rows: list[dict[str, object]],
) -> bool:
    """Validate one answer against all cited rows without enforcing one sentence per row."""
    if not answer.strip() or not row_indices:
        return False
    if len(set(row_indices)) != len(row_indices):
        return False
    if any(index < 0 or index >= len(rows) for index in row_indices):
        return False

    cited_rows = [rows[index] for index in row_indices]
    cited_json = json.dumps(cited_rows, ensure_ascii=False, allow_nan=False)
    if not set(_NUMBER.findall(answer)) <= set(_NUMBER.findall(cited_json)):
        return False

    folded_answer = answer.casefold()
    folded_cited_json = cited_json.casefold()
    cited_strings = [_scalar_strings(row) for row in cited_rows]
    all_cited_strings = set().union(*cited_strings)
    if any(
        token.casefold() not in _SAFE_SENTENCE_TOKENS
        and token.casefold() not in folded_cited_json
        for token in _NAMED_TOKEN.findall(answer)
    ):
        return False

    # Require every cited row to contribute evidence. Shared values (e.g. one coordinator)
    # are valid evidence for all rows; otherwise each row needs at least one visible value.
    shared_strings = (
        set.intersection(*cited_strings) if all(cited_strings) else set()
    )
    for row_strings in cited_strings:
        evidence_strings = row_strings - shared_strings
        if evidence_strings:
            if not any(value in folded_answer for value in evidence_strings):
                return False
        elif shared_strings and not any(value in folded_answer for value in shared_strings):
            return False

    # Do not allow a value from a non-cited row to enter the answer.
    for index, row in enumerate(rows):
        if index in row_indices:
            continue
        foreign_strings = _scalar_strings(row) - all_cited_strings
        if any(value in folded_answer for value in foreign_strings):
            return False

    # Preserve row/metric associations when the answer uses one row-specific value per sentence.
    # A sentence containing several row-specific values is an intentional grouped answer.
    shared_all_rows = (
        set.intersection(*[_scalar_strings(row) for row in cited_rows])
        if cited_rows
        else set()
    )
    for sentence in re.split(r"(?<=[.!?])\s+", answer.strip()):
        sentence_numbers = set(_NUMBER.findall(sentence))
        if not sentence_numbers:
            continue
        matching_rows = [
            index
            for index, row in zip(row_indices, cited_rows, strict=True)
            if any(
                value not in shared_all_rows and value in sentence.casefold()
                for value in _scalar_strings(row)
            )
        ]
        if len(matching_rows) == 1:
            row_numbers = set(
                _NUMBER.findall(json.dumps(rows[matching_rows[0]], ensure_ascii=False))
            )
            if not sentence_numbers <= row_numbers:
                return False
    return True


def _grounded_fallback(rows: list[dict[str, object]], *, total_rows: int) -> str:
    """Render verified rows without inventing context or exposing JSON internals."""

    def render_value(value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, allow_nan=False)

    suffix = "" if len(rows) == total_rows else f" Se muestran {len(rows)} de {total_rows}."
    if not rows:
        return "No se encontraron resultados para esta consulta."

    if all(row.get("brecha_curricular") is True for row in rows):
        visible_fields = [
            key
            for key, value in rows[0].items()
            if key != "brecha_curricular" and isinstance(value, str) and value.strip()
        ]
        if visible_fields:
            dimension_field = next(
                (
                    key
                    for key in visible_fields
                    if any(
                        term in key.casefold()
                        for term in ("herramient", "habilidad", "competencia", "curso")
                    )
                ),
                visible_fields[0],
            )
            gap_values = [
                str(row[dimension_field]).strip()
                for row in rows
                if isinstance(row.get(dimension_field), str)
                and str(row[dimension_field]).strip()
            ]
            if gap_values:
                noun = _result_noun(dimension_field, plural=len(gap_values) != 1)
                sample = gap_values[:3]
                if len(sample) == 1:
                    examples = sample[0]
                elif len(sample) == 2:
                    examples = f"{sample[0]} y {sample[1]}"
                else:
                    examples = f"{sample[0]}, {sample[1]} y {sample[2]}"
                return (
                    f"Encontré {total_rows} {noun} exigidas por el mercado y marcadas como "
                    f"brecha curricular. Entre los primeros resultados aparecen {examples}."
                )

    shared_keys = set(rows[0]) if rows else set()
    if shared_keys and all(set(row) == shared_keys for row in rows):
        text_fields = [
            key
            for key in shared_keys
            if all(isinstance(row.get(key), str) and str(row[key]).strip() for row in rows)
        ]
        numeric_fields = [
            key
            for key in shared_keys
            if all(
                isinstance(row.get(key), (int, float))
                and not isinstance(row.get(key), bool)
                for row in rows
            )
        ]
        if len(text_fields) == 1 and len(numeric_fields) == 1:
            text_field = text_fields[0]
            numeric_field = numeric_fields[0]
            ranked = [
                f"{row[text_field]} ({render_value(row[numeric_field])})"
                for row in rows[:3]
            ]
            if len(ranked) == 1:
                leaders = ranked[0]
            elif len(ranked) == 2:
                leaders = f"{ranked[0]} y {ranked[1]}"
            else:
                leaders = f"{ranked[0]}, {ranked[1]} y {ranked[2]}"
            metric = numeric_field.replace("_", " ")
            metric = re.sub(r"^(cantidad|total)\s+", r"\1 de ", metric)
            return f"El ranking por {metric} está encabezado por {leaders}."

    if all(len(row) == 1 for row in rows):
        fallback_values = [next(iter(row.values())) for row in rows]
        rendered_values = [render_value(value) for value in fallback_values]
        noun = _result_noun(next(iter(rows[0]), ""), plural=len(rendered_values) != 1)
        if len(rendered_values) == 1:
            return f"Encontré 1 {noun} en los datos: {rendered_values[0]}.{suffix}"
        lines = "\n".join(f"- {value}" for value in rendered_values)
        return f"Encontré {len(rendered_values)} {noun} en los datos:\n{lines}{suffix}"

    fallback_lines: list[str] = []
    for row in rows:
        fields = ", ".join(
            f"{key.replace('_', ' ')}: {render_value(value)}"
            for key, value in row.items()
        )
        fallback_lines.append(f"- {fields}")
    rendered_lines = "\n".join(fallback_lines)
    return f"Se encontraron {len(rows)} resultados verificados:\n{rendered_lines}{suffix}"


def _natural_list_answer(rows: list[dict[str, object]]) -> str:
    """Render a readable, schema-driven list when every row has one value."""
    values: list[str] = []
    for row in rows:
        if len(row) != 1:
            return _grounded_fallback(rows, total_rows=len(rows))
        value = next(iter(row.values()))
        values.append(str(value))

    field_name = next(iter(rows[0]), "") if rows else ""
    noun = _result_noun(field_name, plural=len(values) != 1)
    if len(values) == 1:
        return f"Encontré 1 {noun} que coincide con tu consulta: {values[0]}."

    lines = "\n".join(f"- {value}" for value in values)
    return f"Encontré {len(values)} {noun} que coinciden con tu consulta:\n{lines}"


def _result_noun(field_name: str, *, plural: bool = True) -> str:
    """Derive a human label from the returned field instead of hardcoding a domain entity."""
    normalized = re.sub(r"[^a-z0-9áéíóúüñ]+", "_", field_name.casefold()).strip("_")
    if not normalized:
        return "resultados" if plural else "resultado"
    parts = [part for part in normalized.split("_") if part]
    while len(parts) > 1 and parts[0] in {"nombre", "name", "descripcion", "description"}:
        parts.pop(0)
    if not parts or parts[0] in {"total", "count", "cantidad", "numero", "número"}:
        return "resultados" if plural else "resultado"

    singular = parts[-1]
    if singular.endswith(("as", "es", "os", "us")) and len(singular) > 3:
        singular = singular[:-1]
    if not plural:
        return singular
    if singular.endswith("z"):
        return f"{singular[:-1]}ces"
    if singular.endswith(("s", "x")):
        return singular
    if singular.endswith(("a", "e", "i", "o", "u")):
        return f"{singular}s"
    return f"{singular}es"


async def redacta_respuesta(
    estado: Estado,
    *,
    analyst_runnable: AnalystRunnable | None = None,
) -> Estado:
    """Ask the analyst for one interpretive answer and validate its cited rows."""
    if estado.get("error"):
        return {}
    rows = estado.get("filas")
    question = estado.get("pregunta_contextualizada") or estado.get("pregunta")
    if (
        not isinstance(rows, list)
        or not all(isinstance(row, dict) for row in rows)
        or not isinstance(question, str)
        or not question.strip()
    ):
        return {}
    if not rows:
        return {}

    public_rows = _public_rows(rows, question)
    fallback = _grounded_fallback(public_rows, total_rows=len(rows))
    if len(public_rows) > 1 and all(len(row) == 1 for row in public_rows):
        answer = _natural_list_answer(public_rows)
        log_event(
            "grounded_answer",
            "completed",
            rows_count=len(rows),
            displayed_rows=len(public_rows),
            length=len(answer),
            model_driven=False,
        )
        return {"respuesta": answer}
    try:
        messages = [
            SystemMessage(content=build_grounded_analysis_prompt()),
            HumanMessage(
                content=build_grounded_analysis_user_prompt(
                    question,
                    public_rows,
                    total_rows=len(rows),
                )
            ),
        ]
        runnable = analyst_runnable or build_analyst_runnable()
        raw_result = await asyncio.wait_for(
            runnable.ainvoke(messages),
            timeout=_analyst_timeout_seconds(),
        )
        result = GroundedAnalysis.model_validate(raw_result)
        answer = result.respuesta.strip()
    except TimeoutError as exc:
        log_error("grounded_answer", "timeout", exc)
        return {"respuesta": fallback, "error": None, "warning": "analyst_timeout"}
    except Exception as exc:
        log_error("grounded_answer", "failed", exc)
        return {"respuesta": fallback, "error": None, "warning": "analyst_failed"}

    accepted, reason = inspect_response(answer)
    answer_grounded = _answer_is_grounded(answer, result.row_indices, public_rows)
    if not accepted or not answer_grounded:
        log_event(
            "grounded_answer",
            "rejected",
            level="warning",
            reason=reason or "answer is not grounded in its cited rows",
        )
        return {
            "respuesta": fallback,
            "error": None,
            "warning": "analyst_response_rejected",
        }

    log_event(
        "grounded_answer",
        "completed",
        rows_count=len(rows),
        displayed_rows=len(public_rows),
        cited_rows_count=len(result.row_indices),
        length=len(answer),
        model_driven=True,
    )
    return {"respuesta": answer}
