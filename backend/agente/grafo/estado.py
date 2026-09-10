from typing import Any, TypedDict

from agente.utils.neo4j_schema import Neo4jSchemaSnapshot


class Estado(TypedDict, total=False):
    trace_id: str
    pregunta: str
    pregunta_original: str
    pregunta_mejorada: str
    memory_scope: str
    schema: Neo4jSchemaSnapshot
    cypher: str
    parameters: dict[str, Any]
    query_limit: int
    cardinality: str
    entity_resolution: str
    respuesta: str
    filas: list[dict[str, Any]]
    error: str | None
    warning: str | None
    ruta: str


def pregunta_para_procesar(estado: Estado) -> str | None:
    """Return the orchestrator's safe wording, or the original question."""
    improved = estado.get("pregunta_mejorada")
    if isinstance(improved, str) and improved.strip():
        return improved
    original = estado.get("pregunta")
    return original if isinstance(original, str) and original.strip() else None
