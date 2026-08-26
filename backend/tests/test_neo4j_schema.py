from __future__ import annotations

import pytest

import agente.utils.neo4j_schema as neo4j_schema


class FakeGraph:
    get_schema = "schema extraido"
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


class FakeLiveGraph(FakeGraph):
    get_schema = "schema extraido"
    get_structured_schema = {
        "node_props": {
            "Carrera": ["nombre"],
            "Empresa": ["nombre"],
            "Oferta_Laboral": ["titulo"],
        },
        "rel_props": {},
        "relationships": [],
    }


def test_schema_loader_preserves_any_labels_extracted_from_neo4j(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = FakeGraph()
    monkeypatch.setattr(neo4j_schema, "create_schema_graph", lambda: graph)

    snapshot = neo4j_schema.extract_neo4j_schema()

    assert snapshot.text == "schema extraido"
    assert set(snapshot.structured["node_props"]) == {"Empresa"}
    assert graph.closed is True


def test_schema_loader_preserves_the_live_ciar_offer_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = FakeLiveGraph()
    monkeypatch.setattr(neo4j_schema, "create_schema_graph", lambda: graph)

    snapshot = neo4j_schema.extract_neo4j_schema()

    assert snapshot.text == "schema extraido"
    assert set(snapshot.structured["node_props"]) == {
        "Carrera",
        "Empresa",
        "Oferta_Laboral",
    }
    assert graph.closed is True
