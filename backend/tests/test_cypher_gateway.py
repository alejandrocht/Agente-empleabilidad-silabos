from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from neo4j import RoutingControl
from neo4j.exceptions import AuthError, ServiceUnavailable
from neo4j.spatial import WGS84Point
from neo4j.time import Date, DateTime, Duration

from agente.utils.cypher_guard import (
    CypherGuardError,
    guard_cypher,
    validate_parameter_cardinality,
)
from agente.utils.db import (
    AsyncNeo4jQueryGateway,
    Neo4jExplainError,
    Neo4jQueryError,
    Neo4jReadConfig,
    classify_neo4j_error,
    neo4j_diagnostic_context,
    normalize_neo4j_value,
    query_fingerprint,
)
from agente.utils.logger import trace_context

SAFE_QUERY = "MATCH (n:Carrera) RETURN n.nombre AS nombre LIMIT $limit"


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n) RETURN n.name LIMIT 10; MATCH (m) RETURN m.name LIMIT 10",
        "MATCH (n) // hidden write\nRETURN n.name LIMIT 10",
        "MATCH (n) /* hidden write */ RETURN n.name LIMIT 10",
        "MATCH (n) CREATE (:Other) RETURN n.name LIMIT 10",
        "CALL db.labels() YIELD label RETURN label LIMIT 10",
        "SHOW DATABASES RETURN 1 LIMIT 10",
        "MATCH (n) RETURN n.name",
        "RETURN 1 LIMIT 10",
    ],
)
def test_guard_rejects_unprovable_or_unsafe_queries(query: str) -> None:
    with pytest.raises(CypherGuardError):
        guard_cypher(query)


def test_guard_reconciles_parameters_and_proves_bounded_limit() -> None:
    guarded = guard_cypher(SAFE_QUERY, {"limit": 100})

    assert guarded.text == SAFE_QUERY
    assert guarded.parameters == {"limit": 100}
    assert guarded.limit == 100

    with pytest.raises(CypherGuardError, match="Missing"):
        guard_cypher(SAFE_QUERY, {})
    with pytest.raises(CypherGuardError, match="Unexpected"):
        guard_cypher(SAFE_QUERY, {"limit": 10, "extra": True})
    with pytest.raises(CypherGuardError, match="between 1 and 100"):
        guard_cypher(SAFE_QUERY, {"limit": 101})


@pytest.mark.parametrize(
    ("query", "parameters"),
    [
        (
            "MATCH (n:Carrera) WHERE n.id_carrera = $carrera_ids "
            "RETURN n.nombre AS nombre LIMIT 10",
            {"carrera_ids": ["CAR_1"]},
        ),
        (
            "MATCH (n:Carrera) WHERE n.id_carrera IN $carrera_id "
            "RETURN n.nombre AS nombre LIMIT 10",
            {"carrera_id": "CAR_1"},
        ),
    ],
)
def test_guard_rejects_scalar_list_operator_mismatch(
    query: str, parameters: dict[str, Any]
) -> None:
    with pytest.raises(CypherGuardError):
        guard_cypher(query, parameters)
    with pytest.raises(CypherGuardError):
        validate_parameter_cardinality(query, parameters)


@pytest.mark.parametrize(
    ("query", "parameters"),
    [
        (
            "MATCH (i:Industria) WHERE toLower(i.nombre) CONTAINS "
            "toLower($industria_id) RETURN i.nombre AS industria LIMIT 10",
            {"industria_id": "INDU_1"},
        ),
        (
            "MATCH (h:Herramienta) WHERE h.nombre_herramienta CONTAINS "
            "$herramienta_id RETURN h.nombre_herramienta AS herramienta LIMIT 10",
            {"herramienta_id": "HERR_1"},
        ),
        (
            "MATCH (c:Carrera) WHERE c.nombre_carrera = $carrera_id "
            "RETURN c.nombre_carrera AS carrera LIMIT 10",
            {"carrera_id": "CAR_1"},
        ),
        (
            "MATCH (h:Herramienta) WHERE h.nombre_herramienta IN $herramienta_ids "
            "RETURN h.nombre_herramienta AS herramienta LIMIT 10",
            {"herramienta_ids": ["HERR_1", "HERR_2"]},
        ),
    ],
)
def test_guard_rejects_canonical_id_parameters_against_text_properties(
    query: str, parameters: dict[str, Any]
) -> None:
    with pytest.raises(CypherGuardError, match=r"(?i)canonical ID parameter"):
        guard_cypher(query, parameters)


def test_guard_rejects_generic_entity_id_alias_against_canonical_id_property() -> None:
    query = (
        "MATCH (i:Industria) WHERE i.id_industria = $entidad_id "
        "RETURN i.nombre AS industria LIMIT 10"
    )

    with pytest.raises(CypherGuardError, match=r"(?i)canonical ID parameter"):
        guard_cypher(query, {"entidad_id": "INDU_1"})


@pytest.mark.parametrize(
    ("query", "parameters"),
    [
        (
            "MATCH (s:Sector) WHERE s.nombre CONTAINS $sector_id "
            "RETURN s.nombre AS sector LIMIT 10",
            {"sector_id": "SEC_1"},
        ),
        (
            "MATCH (s:Sector) WHERE toLower(s.descripcion) = toLower($sector_id) "
            "RETURN s.nombre AS sector LIMIT 10",
            {"sector_id": "SEC_1"},
        ),
        (
            "MATCH (s:Sector) WHERE s.nombre IN $sector_ids "
            "RETURN s.nombre AS sector LIMIT 10",
            {"sector_ids": ["SEC_1"]},
        ),
    ],
)
def test_guard_rejects_unknown_id_like_parameters_against_text_semantics(
    query: str, parameters: dict[str, Any]
) -> None:
    with pytest.raises(CypherGuardError, match=r"(?i)ID-like parameter"):
        guard_cypher(query, parameters)


@pytest.mark.parametrize(
    ("query", "parameters"),
    [
        (
            "MATCH (s:Sector) WHERE s.id_sector = $sector_id "
            "RETURN s.nombre AS sector LIMIT 10",
            {"sector_id": "SEC_1"},
        ),
        (
            "MATCH (s:Sector) WHERE s.external_id IN $sector_ids "
            "RETURN s.nombre AS sector LIMIT 10",
            {"sector_ids": ["SEC_1", "SEC_2"]},
        ),
    ],
)
def test_guard_accepts_unknown_id_like_parameters_on_id_shaped_properties(
    query: str, parameters: dict[str, Any]
) -> None:
    assert guard_cypher(query, parameters).parameters == parameters


def test_guard_allows_non_entity_id_like_metadata_when_it_is_not_a_text_filter() -> None:
    query = "MATCH (s:Sector) RETURN s.nombre AS sector, $correlation_id AS request LIMIT 10"

    assert guard_cypher(query, {"correlation_id": "request-7"}).parameters == {
        "correlation_id": "request-7"
    }


@pytest.mark.parametrize(
    "query",
    [
        (
            "MATCH (i:Industria) "
            "RETURN 'i.id_industria = $industria_id' AS proof, "
            "$industria_id AS supplied LIMIT 10"
        ),
        (
            "MATCH (i:Industria) "
            "RETURN {id_industria: $industria_id} AS proof LIMIT 10"
        ),
    ],
)
def test_guard_rejects_literal_or_projection_map_as_canonical_id_filter(query: str) -> None:
    with pytest.raises(CypherGuardError, match=r"(?i)canonical ID parameter"):
        guard_cypher(query, {"industria_id": "INDU_1"})


def test_guard_id_semantics_property_loop_covers_256_token_and_map_variants() -> None:
    for index in range(256):
        variable = f"node_{index}"
        parameter = f"sector_{index}_id"
        property_name = f"id_sector_{index}"

        text_query = (
            f"MATCH ({variable}:Sector) WHERE {variable}.nombre CONTAINS ${parameter} "
            f"RETURN {variable}.nombre AS value LIMIT 10"
        )
        with pytest.raises(CypherGuardError, match=r"(?i)ID-like parameter"):
            guard_cypher(text_query, {parameter: index})

        valid_unknown_query = (
            f"MATCH ({variable}:Sector) WHERE {variable}.{property_name} = ${parameter} "
            f"RETURN {variable}.nombre AS value LIMIT 10"
        )
        assert guard_cypher(valid_unknown_query, {parameter: index}).parameters == {
            parameter: index
        }

        literal_query = (
            f"MATCH ({variable}:Industria) RETURN "
            f"'{variable}.id_industria = $industria_id proof_{index}' AS proof, "
            "$industria_id AS supplied LIMIT 10"
        )
        with pytest.raises(CypherGuardError, match=r"(?i)canonical ID parameter"):
            guard_cypher(literal_query, {"industria_id": f"INDU_{index}"})

        projection_map_query = (
            f"MATCH ({variable}:Industria) "
            f"RETURN {{id_industria: $industria_id, sample: {index}}} AS proof LIMIT 10"
        )
        with pytest.raises(CypherGuardError, match=r"(?i)canonical ID parameter"):
            guard_cypher(projection_map_query, {"industria_id": f"INDU_{index}"})

        pattern_map_query = (
            f"MATCH ({variable}:Industria {{id_industria: $industria_id}}) "
            f"RETURN {variable}.nombre AS value LIMIT 10"
        )
        assert guard_cypher(
            pattern_map_query, {"industria_id": f"INDU_{index}"}
        ).limit == 10


def test_guard_rejects_unprojected_order_by_aggregate() -> None:
    query = (
        "MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
        "RETURN i.nombre AS industria, count(DISTINCT o) AS total_ofertas "
        "ORDER BY max(o.fecha_publicacion) DESC LIMIT 20"
    )

    with pytest.raises(CypherGuardError, match="ORDER BY aggregate"):
        guard_cypher(query)


@pytest.mark.parametrize(
    ("query", "parameters"),
    [
        (
            "MATCH (i:Industria) WHERE i.id_industria = $industria_id "
            "RETURN i.nombre AS industria LIMIT 10",
            {"industria_id": "INDU_1"},
        ),
        (
            "MATCH (h:Herramienta) WHERE h.id_herramienta IN $herramienta_ids "
            "RETURN h.nombre_herramienta AS herramienta LIMIT 10",
            {"herramienta_ids": ["HERR_1", "HERR_2"]},
        ),
        (
            "MATCH (c:Carrera) WHERE $carrera_id = c.id_carrera "
            "RETURN c.nombre_carrera AS carrera LIMIT 10",
            {"carrera_id": "CAR_1"},
        ),
        (
            "MATCH (c:Carrera {id_carrera: $carrera_id}) "
            "RETURN c.nombre_carrera AS carrera LIMIT 10",
            {"carrera_id": "CAR_1"},
        ),
    ],
)
def test_guard_accepts_canonical_entity_parameter_contract(
    query: str, parameters: dict[str, Any]
) -> None:
    assert guard_cypher(query, parameters).parameters == parameters


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n:Carrera) RETURN n LIMIT 10",
        "MATCH ()-[r:REL]->() RETURN DISTINCT r AS relation LIMIT 10",
    ],
)
def test_guard_rejects_provable_complete_graph_entities(query: str) -> None:
    with pytest.raises(CypherGuardError, match="complete node or relationship"):
        guard_cypher(query)


def test_guard_allows_scalars_maps_and_aggregates() -> None:
    queries = [
        "MATCH (n:Carrera) RETURN n.name, count(n) AS total LIMIT 10",
        "MATCH (n:Carrera) RETURN {name: n.name} AS carrera LIMIT 10",
        "UNWIND $items AS item RETURN item LIMIT $limit",
    ]

    assert guard_cypher(queries[0]).limit == 10
    assert guard_cypher(queries[1]).limit == 10
    assert guard_cypher(queries[2], {"items": [1], "limit": 10}).limit == 10


@dataclass
class FakeRecord:
    value: dict[str, Any]

    def data(self) -> dict[str, Any]:
        return self.value


class FakeAsyncDriver:
    def __init__(self, results: list[object]):
        self.results = results
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def execute_query(self, query: object, **kwargs: object) -> object:
        self.calls.append({"query": query, **kwargs})
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self) -> None:
        self.closed = True


def read_result(*records: FakeRecord, notifications: tuple[object, ...] = ()) -> object:
    summary = SimpleNamespace(query_type="r", gql_status_objects=notifications)
    return SimpleNamespace(records=list(records), summary=summary)


def test_gateway_explains_before_execution_with_same_parameters_and_read_routing() -> None:
    driver = FakeAsyncDriver(
        [
            read_result(),
            read_result(FakeRecord({"name": "Ingenieria"})),
        ]
    )
    config = Neo4jReadConfig(
        uri="neo4j://unused",
        user="reader",
        password="secret",
        database="ciar",
        timeout_seconds=7.5,
    )
    gateway = AsyncNeo4jQueryGateway(driver, config)

    rows = asyncio.run(gateway.run(SAFE_QUERY, {"limit": 10}))

    assert rows == [{"name": "Ingenieria"}]
    assert [call["query"].text for call in driver.calls] == [
        f"EXPLAIN {SAFE_QUERY}",
        SAFE_QUERY,
    ]
    assert all(call["query"].timeout == 7.5 for call in driver.calls)
    assert all(call["parameters_"] == {"limit": 10} for call in driver.calls)
    assert all(call["routing_"] is RoutingControl.READ for call in driver.calls)
    assert all(call["database_"] == "ciar" for call in driver.calls)


def test_gateway_fulltext_search_is_schema_bound_and_read_only() -> None:
    driver = FakeAsyncDriver(
        [
            read_result(),
            read_result(
                FakeRecord(
                    {
                        "name": "curso_coordinador_ft",
                        "labelsOrTypes": ["Curso"],
                        "properties": ["coordinador"],
                        "state": "ONLINE",
                    }
                )
            ),
            read_result(),
            read_result(FakeRecord({"value": "Ángela Mayhua", "score": 0.9})),
        ]
    )
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")
    gateway = AsyncNeo4jQueryGateway(driver, config)

    rows = asyncio.run(
        gateway.search_fulltext(
            label="Curso",
            property_name="coordinador",
            query="angla~2 AND mayhua~2",
            limit=10,
        )
    )

    assert rows == [{"value": "Ángela Mayhua", "score": 0.9}]
    assert [call["query"].text for call in driver.calls] == [
        "EXPLAIN SHOW FULLTEXT INDEXES YIELD name, labelsOrTypes, properties, state "
        "RETURN name, labelsOrTypes, properties, state LIMIT 100",
        "SHOW FULLTEXT INDEXES YIELD name, labelsOrTypes, properties, state "
        "RETURN name, labelsOrTypes, properties, state LIMIT 100",
        "EXPLAIN CALL db.index.fulltext.queryNodes($index_name, $query_text, "
        "{limit: $fulltext_limit}) YIELD node, score "
        "WHERE $node_label IN labels(node) "
        "RETURN node.coordinador AS value, score",
        "CALL db.index.fulltext.queryNodes($index_name, $query_text, "
        "{limit: $fulltext_limit}) YIELD node, score "
        "WHERE $node_label IN labels(node) "
        "RETURN node.coordinador AS value, score",
    ]
    assert driver.calls[3]["parameters_"] == {
        "index_name": "curso_coordinador_ft",
        "query_text": "coordinador:angla~2 AND coordinador:mayhua~2",
        "fulltext_limit": 10,
        "node_label": "Curso",
    }
    assert all(call["routing_"] is RoutingControl.READ for call in driver.calls)


def test_gateway_fulltext_search_caches_index_metadata_for_gateway_lifecycle() -> None:
    index_row = FakeRecord(
        {
            "name": "curso_coordinador_ft",
            "labelsOrTypes": ["Curso"],
            "properties": ["coordinador"],
            "state": "ONLINE",
        }
    )
    driver = FakeAsyncDriver(
        [
            read_result(),
            read_result(index_row),
            read_result(),
            read_result(FakeRecord({"value": "Ángela Mayhua", "score": 0.9})),
            read_result(),
            read_result(FakeRecord({"value": "Carlos Pérez", "score": 0.8})),
        ]
    )
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")
    gateway = AsyncNeo4jQueryGateway(driver, config)

    async def search_twice() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        first = await gateway.search_fulltext(
            label="Curso",
            property_name="coordinador",
            query="angela~2 AND mayhua~2",
            limit=10,
        )
        second = await gateway.search_fulltext(
            label="Curso",
            property_name="coordinador",
            query="carlos~2 AND perez~2",
            limit=10,
        )
        return first, second

    first, second = asyncio.run(search_twice())

    assert first == [{"value": "Ángela Mayhua", "score": 0.9}]
    assert second == [{"value": "Carlos Pérez", "score": 0.8}]
    assert sum("FULLTEXT INDEXES" in call["query"].text for call in driver.calls) == 2
    assert len(driver.calls) == 6


def test_gateway_fulltext_search_falls_back_when_matching_index_is_absent() -> None:
    driver = FakeAsyncDriver(
        [
            read_result(),
            read_result(
                FakeRecord(
                    {
                        "name": "otro_indice",
                        "labelsOrTypes": ["Profesor"],
                        "properties": ["nombre"],
                        "state": "ONLINE",
                    }
                )
            ),
            read_result(),
        ]
    )
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")

    rows = asyncio.run(
        AsyncNeo4jQueryGateway(driver, config).search_fulltext(
            label="Curso",
            property_name="coordinador",
            query="angla~2 AND mayhua~2",
            limit=10,
        )
    )

    assert rows == []
    assert len(driver.calls) == 2


def test_gateway_fulltext_search_rejects_unbounded_lucene_syntax() -> None:
    driver = FakeAsyncDriver([])
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")

    with pytest.raises(Neo4jQueryError, match="Invalid full-text query"):
        asyncio.run(
            AsyncNeo4jQueryGateway(driver, config).search_fulltext(
                label="Curso",
                property_name="coordinador",
                query="*",
                limit=10,
            )
        )

    assert driver.calls == []


def test_gateway_logs_guard_explain_execution_and_redacts_parameter_values(capsys) -> None:
    driver = FakeAsyncDriver(
        [
            read_result(),
            read_result(FakeRecord({"name": "Ingenieria"})),
        ]
    )
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")

    with trace_context("abcdefabcdefabcdefabcdefabcdefab"):
        asyncio.run(
            AsyncNeo4jQueryGateway(driver, config).run(
                "MATCH (n:Carrera) WHERE n.nombre = $name "
                "RETURN n.nombre AS nombre LIMIT $limit",
                {"name": "PRIVATE_NAME", "limit": 10},
            )
        )

    entries = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    events = {entry["event"] for entry in entries}
    serialized = json.dumps(entries)

    assert {
        "validation_started",
        "validation_completed",
        "explain_started",
        "explain_completed",
        "execution_started",
        "execution_completed",
    } <= events
    assert all(
        entry["context"]["trace_id"] == "abcdefabcdefabcdefabcdefabcdefab"
        for entry in entries
    )
    assert "PRIVATE_NAME" not in serialized
    assert all(entry["context"].get("read_only") is not False for entry in entries)


def test_gateway_fails_after_explain_schema_warning_without_execution() -> None:
    warning = SimpleNamespace(
        is_notification=True,
        raw_severity="WARNING",
        raw_classification="SCHEMA",
    )
    driver = FakeAsyncDriver([read_result(notifications=(warning,))])
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")

    with pytest.raises(Neo4jQueryError, match="schema warning"):
        asyncio.run(AsyncNeo4jQueryGateway(driver, config).run(SAFE_QUERY, {"limit": 10}))

    assert len(driver.calls) == 1


def test_gateway_classifies_syntax_failure_at_explain_boundary() -> None:
    from neo4j.exceptions import CypherSyntaxError

    driver = FakeAsyncDriver([CypherSyntaxError("PRIVATE_SYNTAX")])
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")

    with pytest.raises(Neo4jExplainError) as error:
        asyncio.run(AsyncNeo4jQueryGateway(driver, config).run(SAFE_QUERY, {"limit": 10}))

    assert error.value.category == "syntax"
    assert str(error.value) == "Neo4j EXPLAIN rejected the read query"
    assert len(driver.calls) == 1


@pytest.mark.parametrize(
    ("error", "category", "classification"),
    [
        (AuthError("PRIVATE_AUTH"), "auth", "auth_error"),
        (ServiceUnavailable("PRIVATE_TRANSPORT"), "transport", "transport_error"),
    ],
)
def test_neo4j_diagnostics_classify_auth_and_transport_without_messages(
    error: Exception,
    category: str,
    classification: str,
) -> None:
    diagnostic = classify_neo4j_error(error)

    assert diagnostic.category == category
    assert diagnostic.classification == classification
    assert diagnostic.code is None or diagnostic.code.startswith("Neo.")
    context = neo4j_diagnostic_context(
        stage="dynamic_explain",
        duration_ms=12.5,
        cypher=SAFE_QUERY,
        error=error,
    )
    assert context["neo4j_category"] == category
    assert context["neo4j_classification"] == classification
    assert "PRIVATE_" not in json.dumps(context)


def test_query_fingerprint_is_stable_and_payload_free() -> None:
    query = "MATCH (n:Carrera) RETURN n.nombre AS nombre LIMIT 10"

    assert query_fingerprint(query) == (
        "0f8be4e9e979f1c89723176f3346460fa58a841d3ecba76eff99f2087e4e307c"
    )
    assert query_fingerprint(query) == query_fingerprint(query)
    assert query_fingerprint(query) != query_fingerprint(query + " ")
    assert len(query_fingerprint(query)) == 64


def test_read_config_rejects_partially_configured_dedicated_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_READ_URI", "neo4j://reader")
    monkeypatch.delenv("NEO4J_READ_USER", raising=False)
    monkeypatch.delenv("NEO4J_READ_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="configured together"):
        Neo4jReadConfig.from_env()


def test_read_config_prefers_complete_dedicated_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEO4J_READ_URI", "neo4j://reader")
    monkeypatch.setenv("NEO4J_READ_USER", "domain-reader")
    monkeypatch.setenv("NEO4J_READ_PASSWORD", "read-secret")
    monkeypatch.setenv("NEO4J_READ_DATABASE", "domain")
    monkeypatch.setenv("NEO4J_URI", "neo4j://legacy")
    monkeypatch.setenv("NEO4J_USER", "legacy")
    monkeypatch.setenv("NEO4J_PASSWORD", "legacy-secret")

    config = Neo4jReadConfig.from_env()

    assert (config.uri, config.user, config.password, config.database) == (
        "neo4j://reader",
        "domain-reader",
        "read-secret",
        "domain",
    )
    assert config.uses_legacy_credentials is False


def test_owned_gateway_closes_fake_async_driver() -> None:
    driver = FakeAsyncDriver([])
    config = Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar")
    gateway = AsyncNeo4jQueryGateway(driver, config, owns_driver=True)

    async def use_gateway() -> None:
        async with gateway:
            pass

    asyncio.run(use_gateway())

    assert driver.closed is True


def test_normalization_handles_nested_temporal_spatial_and_nonfinite_values() -> None:
    value = {
        "date": Date(2025, 1, 2),
        "datetime": DateTime(2025, 1, 2, 3, 4, 5),
        "duration": Duration(months=1, days=2, seconds=3),
        "point": WGS84Point((1.5, -2.5)),
        "nested": [{"value": float("inf")}],
    }

    normalized = normalize_neo4j_value(value)

    assert normalized == {
        "date": "2025-01-02",
        "datetime": "2025-01-02T03:04:05.000000000",
        "duration": "P1M2DT3S",
        "point": {
            "type": "WGS84Point",
            "coordinates": [1.5, -2.5],
            "srid": 4326,
        },
        "nested": [{"value": "inf"}],
    }
    assert json.loads(json.dumps(normalized, allow_nan=False)) == normalized
