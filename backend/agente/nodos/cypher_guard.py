"""Final fail-closed Cypher guard seam before Neo4j execution."""

from __future__ import annotations

from collections.abc import Mapping

from agente.grafo.estado import Estado
from agente.nodos.devuelve_respuesta import SAFE_QUERY_ERROR
from agente.utils.cypher_guard import CypherGuardError, guard_cypher
from agente.utils.logger import log_error, log_event
from agente.utils.verbose import verbose_step


def cypher_guard(estado: Estado) -> Estado:
    """Accept only a guarded query and normalized parameters for the gateway."""
    if estado.get("error"):
        return {}

    cypher = estado.get("cypher")
    parameters = estado.get("parameters")
    if not isinstance(cypher, str) or not isinstance(parameters, Mapping):
        return {
            "respuesta": SAFE_QUERY_ERROR,
            "filas": [],
            "error": "cypher_guard_failed",
        }

    try:
        guarded = guard_cypher(cypher, parameters)
    except CypherGuardError as exc:
        verbose_step("cypher_guard", "Consulta rechazada")
        log_error(
            "cypher_guard",
            "rejected",
            exc,
            step="cypher_guard",
            status="failed",
            guard_decision="rejected",
        )
        return {
            "respuesta": SAFE_QUERY_ERROR,
            "filas": [],
            "error": "cypher_guard_failed",
        }

    log_event(
        "cypher_guard",
        "accepted",
        step="cypher_guard",
        status="success",
        guard_decision="accepted",
        read_only=True,
        query_limit=guarded.limit,
        parameter_names=sorted(guarded.parameters),
        parameter_count=len(guarded.parameters),
    )
    return {
        "cypher": guarded.text,
        "parameters": guarded.parameters,
        "query_limit": guarded.limit,
        "error": None,
    }
