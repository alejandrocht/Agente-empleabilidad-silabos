"""Execute the validated read query and build a deterministic public answer."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Protocol, cast

from agente.grafo.estado import Estado
from agente.utils.db import normalize_neo4j_value, open_query_gateway, run_gateway_with_diagnostics
from agente.utils.logger import log_error, log_event
from agente.utils.verbose import verbose_label

SAFE_QUERY_ERROR = (
    "No pude consultar la información de forma segura en este momento. "
    "Intentá nuevamente más tarde."
)
NO_RESULTS_RESPONSE = (
    "No encontré datos relacionados dentro del alcance académico y de empleabilidad del agente "
    "CIAR. Prueba con carreras, cursos, facultades, empresas, ofertas, puestos, herramientas o "
    "competencias."
)


class ReadQueryGateway(Protocol):
    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...


def _deterministic_response(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return NO_RESULTS_RESPONSE
    count = len(rows)
    suffix = "resultado" if count == 1 else "resultados"
    return f"Encontré {count} {suffix} para tu consulta."


async def devuelve_respuesta(
    estado: Estado,
    *,
    query_gateway: ReadQueryGateway | None = None,
) -> Estado:
    """Run only the validated query and expose bounded rows plus a safe answer."""
    if estado.get("error"):
        log_event(
            "query_response",
            "skipped",
            status="skipped",
            input_keys=sorted(estado),
            output_keys=["respuesta", "filas"],
        )
        return {
            "respuesta": estado.get("respuesta", SAFE_QUERY_ERROR),
            "filas": estado.get("filas", []),
        }

    cypher = estado.get("cypher")
    parameters = estado.get("parameters")
    limit = estado.get("query_limit")
    if (
        not isinstance(cypher, str)
        or not isinstance(parameters, dict)
        or not isinstance(limit, int)
    ):
        log_event(
            "query_response",
            "query_missing",
            status="failed",
            input_keys=sorted(estado),
            output_keys=["respuesta", "filas", "error"],
        )
        return {"respuesta": SAFE_QUERY_ERROR, "filas": [], "error": "query_missing"}

    started_at = time.perf_counter()
    parameter_names = sorted(name for name in parameters if isinstance(name, str))
    verbose_label("devuelve_respuesta", "Longitud de Cypher enviado", len(cypher))
    verbose_label("devuelve_respuesta", "Nombres de parámetros enviados", sorted(parameters))
    verbose_label("devuelve_respuesta", "Límite de filas", limit)
    log_event(
        "query_response",
        "query_sent",
        status="structured",
        input_keys=["cypher", "parameters", "query_limit"],
        output_keys=["neo4j_read"],
        query_structure=cypher,
        query_length=len(cypher),
        parameter_names=parameter_names,
        parameter_count=len(parameters),
        read_only=True,
        query_limit=limit,
    )
    try:
        if query_gateway is None:
            async with open_query_gateway() as gateway:
                rows = await run_gateway_with_diagnostics(
                    gateway, cypher, parameters, stage="dynamic_explain"
                )
        else:
            rows = await run_gateway_with_diagnostics(
                query_gateway, cypher, parameters, stage="dynamic_explain"
            )
        normalized = normalize_neo4j_value(rows)
        if not isinstance(normalized, list) or not all(
            isinstance(row, dict) for row in normalized
        ):
            raise TypeError("Query gateway returned an invalid row collection")
    except Exception as exc:
        log_error(
            "query_response",
            "execution_failed",
            exc,
            status="failed",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            input_keys=["cypher", "parameters"],
        )
        return {"respuesta": SAFE_QUERY_ERROR, "filas": [], "error": "query_failed"}

    bounded_rows = cast(list[dict[str, Any]], normalized[:limit])
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    verbose_label("devuelve_respuesta", "Filas crudas devueltas por Neo4j", rows)
    verbose_label("devuelve_respuesta", "Filas normalizadas y acotadas", bounded_rows)
    log_event(
        "query_response",
        "normalization_completed",
        status="success",
        duration_ms=duration_ms,
        rows_count=len(bounded_rows),
        output_keys=["filas"],
    )
    response = _deterministic_response(bounded_rows)
    verbose_label("devuelve_respuesta", "Respuesta determinista generada", response)
    log_event(
        "query_response",
        "response_ready",
        status="success",
        duration_ms=duration_ms,
        rows_count=len(bounded_rows),
        output_keys=["respuesta", "filas", "error"],
        output_size=len(response),
    )
    return {
        "respuesta": response,
        "filas": bounded_rows,
        "error": None,
    }
