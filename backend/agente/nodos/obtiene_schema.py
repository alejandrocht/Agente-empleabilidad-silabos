"""Load the ephemeral Neo4j schema snapshot for the current question."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from agente.grafo.estado import Estado
from agente.utils.logger import log_error, log_event
from agente.utils.neo4j_schema import Neo4jSchemaSnapshot, get_cached_neo4j_schema
from agente.utils.verbose import verbose_step

SchemaLoader = Callable[[], Neo4jSchemaSnapshot]
SCHEMA_LOAD_ERROR = "schema_unavailable"
SAFE_SCHEMA_ERROR = (
    "La fuente de datos de empleabilidad no está disponible o no corresponde al grafo CIAR. "
    "Verificá la conexión de Neo4j e intentá nuevamente."
)


async def obtiene_schema(
    estado: Estado,
    *,
    schema_loader: SchemaLoader | None = None,
) -> Estado:
    """Load schema off the event loop and retain it only in internal graph state."""
    if estado.get("error"):
        return {}

    started_at = time.perf_counter()
    log_event(
        "neo4j_schema",
        "load_started",
        input_keys=["pregunta"],
        status="structured",
    )
    try:
        loader = schema_loader or get_cached_neo4j_schema
        snapshot = await asyncio.to_thread(loader)
    except Exception as exc:
        log_error(
            "neo4j_schema",
            "load_failed",
            exc,
            status="failed",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return {"respuesta": SAFE_SCHEMA_ERROR, "filas": [], "error": SCHEMA_LOAD_ERROR}

    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    verbose_step(
        "obtiene_schema",
        "Schema cargado",
        snapshot.structured,
        duration_ms=duration_ms,
    )
    log_event(
        "neo4j_schema",
        "load_completed",
        status="success",
        duration_ms=duration_ms,
        schema_nodes=len(snapshot.structured.get("node_props", {})),
        schema_relationships=len(snapshot.structured.get("relationships", [])),
        schema_text_length=len(snapshot.text),
        output_keys=["schema"],
    )
    return {"schema": snapshot}
