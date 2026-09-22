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


def test_runtime_schema_loader_uses_the_static_ciar_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        neo4j_schema,
        "create_schema_graph",
        lambda: (_ for _ in ()).throw(AssertionError("live schema must not load")),
    )

    snapshot = neo4j_schema.get_cached_neo4j_schema(force_refresh=True)

    assert set(snapshot.structured["node_props"]) == {
        "Facultad",
        "Carrera",
        "Logros",
        "Curso",
        "Cobertura_Curricular",
        "Industria",
        "Oferta_Laboral",
        "competencia_tecnica",
        "Requerimiento_Laboral",
        "Puesto",
        "Empresa",
        "Silabo",
    }
    assert {
        (item["start"], item["type"], item["end"])
        for item in snapshot.structured["relationships"]
    } >= {
        ("Cobertura_Curricular", "CUBRE", "Logros"),
        ("Cobertura_Curricular", "CUBRE", "competencia_tecnica"),
        ("Curso", "DESARROLLA", "competencia_tecnica"),
    }
