from __future__ import annotations

import pytest

import agente.utils.neo4j_schema as neo4j_schema


class FakeGraph:
    get_schema = "schema ajeno a CIAR"
    get_structured_schema = {
        "node_props": {"Empresa": ["nombre"]},
        "rel_props": {},
        "relationships": [],
    }

    def __init__(self) -> None:
        self.closed = False

    def refresh_schema(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_schema_loader_rechaza_una_base_que_no_es_la_de_ciar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = FakeGraph()
    monkeypatch.setattr(neo4j_schema, "create_schema_graph", lambda: graph)

    with pytest.raises(ValueError, match="CIAR"):
        neo4j_schema.extract_neo4j_schema()

    assert graph.closed is True
