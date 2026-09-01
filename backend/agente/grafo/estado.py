from typing import Any, TypedDict

from agente.utils.neo4j_schema import Neo4jSchemaSnapshot


class Estado(TypedDict, total=False):
    trace_id: str
    pregunta: str
    # Legacy compatibility field; the active graph does not populate it while
    # conversational contextualization remains disabled.
    pregunta_contextualizada: str
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
