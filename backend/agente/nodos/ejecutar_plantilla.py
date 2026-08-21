"""Async executor for immutable, catalog-backed Cypher templates."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Protocol

from agente.cache.consultas import QueryResultCache
from agente.grafo.estado import Estado
from agente.utils.cypher_guard import guard_cypher
from agente.utils.db import normalize_neo4j_value, open_query_gateway
from agente.utils.entity_resolver import EntityResolutionGateway, resolve_template_parameters
from agente.utils.logger import log_error, log_event
from agente.utils.tooler import get_template, validate_template_parameters

SAFE_QUERY_ERROR = (
    "No pude consultar la información en este momento. Intentá nuevamente más tarde."
)


class TemplateQueryGateway(Protocol):
    """Minimal async gateway contract for deterministic no-network tests."""

    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...


def _parameter_clarification(error: ValueError) -> str:
    return f"Necesito corregir los parámetros de la consulta: {error}."


async def ejecutar_plantilla(
    estado: Estado,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    entity_gateway: EntityResolutionGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> Estado:
    """Validate one catalog choice, execute it safely, and retain bounded rows."""
    plan = estado["plan"]
    template_id = plan.template_id
    if template_id is None:
        return {
            "respuesta": "Necesito una plantilla válida para realizar la consulta.",
            "filas": [],
            "error": "template_plan_invalid",
        }

    started_at = time.perf_counter()
    log_event("template_query", "started")
    try:
        template = get_template(template_id)
        resolved_parameters = await resolve_template_parameters(
            plan.parametros,
            query_gateway=entity_gateway or query_gateway,
        )
        if resolved_parameters is None:
            raise ValueError("No pude identificar una entidad única para esa consulta")
        parameters = validate_template_parameters(template_id, resolved_parameters)
        guarded = guard_cypher(template.cypher, parameters)
        log_event("template_query", "validated", configured=True)
    except ValueError as exc:
        log_error("template_query", "parameters_invalid", exc)
        return {
            "respuesta": _parameter_clarification(exc),
            "filas": [],
            "error": "template_parameters_invalid",
        }

    if result_cache is not None:
        cached_rows = result_cache.get(guarded)
        if cached_rows is not None:
            log_event("template_query", "cache_hit", cache_state="hit")
            return {"respuesta": "", "filas": cached_rows}

    try:
        if query_gateway is None:
            async with open_query_gateway() as gateway:
                rows = await gateway.run(guarded.text, guarded.parameters)
        else:
            rows = await query_gateway.run(guarded.text, guarded.parameters)
        normalized = normalize_neo4j_value(rows)
        if not isinstance(normalized, list) or not all(
            isinstance(row, dict) for row in normalized
        ):
            raise TypeError("Query gateway returned an invalid row collection")
    except Exception as exc:
        log_error(
            "template_query",
            "failed",
            exc,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return {
            "respuesta": SAFE_QUERY_ERROR,
            "filas": [],
            "error": "template_query_failed",
        }

    bounded_rows = normalized[: guarded.limit]
    if result_cache is not None:
        result_cache.put(guarded, bounded_rows)
    log_event(
        "template_query",
        "completed",
        rows_count=len(bounded_rows),
        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
    )
    return {"respuesta": "", "filas": bounded_rows}
