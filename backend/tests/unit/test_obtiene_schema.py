from __future__ import annotations

import asyncio

from agente.nodos.obtiene_schema import obtiene_schema
from agente.utils import neo4j_schema


def test_schema_node_reports_an_incompatible_reachable_graph_distinctly() -> None:
    def load_incompatible_schema() -> neo4j_schema.Neo4jSchemaSnapshot:
        raise neo4j_schema.Neo4jSchemaMismatchError(["OfertaLaboral"])

    result = asyncio.run(obtiene_schema({}, schema_loader=load_incompatible_schema))

    assert result == {
        "respuesta": (
            "La fuente de datos de empleabilidad está disponible, "
            "pero no corresponde al grafo CIAR esperado."
        ),
        "filas": [],
        "error": "schema_mismatch",
    }


def test_schema_node_keeps_connectivity_failures_as_unavailable() -> None:
    def fail_connection() -> neo4j_schema.Neo4jSchemaSnapshot:
        raise ConnectionError("transport unavailable")

    result = asyncio.run(obtiene_schema({}, schema_loader=fail_connection))

    assert result["error"] == "schema_unavailable"
    assert result["filas"] == []
