"""Resolve generated entity candidates before the final Cypher guard."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from agente.grafo.estado import Estado
from agente.utils.entity_resolver import (
    EntityResolutionGateway,
    normalize_entity_text_parameters,
    reconcile_entity_parameters,
    resolve_plan_parameters_result,
)
from agente.utils.logger import log_error, log_event

SAFE_ENTITY_RESOLUTION_ERROR = "No pude identificar una entidad válida para esa consulta."
Cardinality = Literal["one", "many"]


async def resuelve_entidades(
    estado: Estado,
    *,
    entity_gateway: EntityResolutionGateway | None = None,
) -> Estado:
    """Hydrate only trusted generated parameters, then leave the final guard in charge."""
    if estado.get("error"):
        return {}

    parameters = estado.get("parameters")
    snapshot = estado.get("schema")
    if not isinstance(parameters, Mapping) or snapshot is None:
        log_error(
            "entity_resolution",
            "state_invalid",
            ValueError("state_invalid"),
            status="failed",
        )
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
        }

    cardinality = estado.get("cardinality")
    if cardinality is None:
        cardinality = (
            "many"
            if any(
                parameter.endswith("_ids") and isinstance(value, (list, tuple))
                for parameter, value in parameters.items()
            )
            else "one"
        )
    if cardinality not in {"one", "many"}:
        log_error(
            "entity_resolution",
            "cardinality_invalid",
            ValueError("cardinality_invalid"),
            status="failed",
        )
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
        }

    cardinality = cast(Cardinality, cardinality)

    schema = getattr(snapshot, "structured", None)
    if not isinstance(schema, Mapping):
        log_error(
            "entity_resolution",
            "schema_invalid",
            ValueError("schema_invalid"),
            status="failed",
        )
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
        }

    cypher = estado.get("cypher")
    if not isinstance(cypher, str):
        log_error(
            "entity_resolution",
            "cypher_invalid",
            ValueError("cypher_invalid"),
            status="failed",
        )
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
        }

    cypher, parameters = normalize_entity_text_parameters(cypher, parameters, schema)

    log_event(
        "entity_resolution",
        "started",
        parameter_names=sorted(str(name) for name in parameters),
        parameter_count=len(parameters),
        cardinality=cardinality,
    )
    try:
        result = await resolve_plan_parameters_result(
            parameters,
            cardinality=cardinality,
            query_gateway=entity_gateway,
            schema=schema,
        )
    except Exception as exc:
        log_error("entity_resolution", "failed", exc, status="failed")
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
        }

    if result.status == "not_found" or (result.status == "multiple" and cardinality == "one"):
        log_event(
            "entity_resolution",
            "rejected",
            status=result.status,
            cardinality=cardinality,
        )
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
            "entity_resolution": result.status,
        }

    try:
        reconciled_cypher, reconciled_parameters = reconcile_entity_parameters(
            cypher,
            parameters,
            result.parameters,
            cardinality=cardinality,
        )
    except (TypeError, ValueError) as exc:
        log_error(
            "entity_resolution",
            "parameter_reconciliation_failed",
            exc,
            status="failed",
        )
        return {
            "respuesta": SAFE_ENTITY_RESOLUTION_ERROR,
            "filas": [],
            "error": "entity_resolution_failed",
        }

    log_event(
        "entity_resolution",
        "completed",
        status=result.status,
        cardinality=cardinality,
        parameter_names=sorted(reconciled_parameters),
    )
    return {
        "cypher": reconciled_cypher,
        "parameters": reconciled_parameters,
        "entity_resolution": result.status,
        "error": None,
    }
