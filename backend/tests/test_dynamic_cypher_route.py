from __future__ import annotations

import asyncio
import importlib
import json
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from neo4j.exceptions import AuthError, CypherSyntaxError, ServiceUnavailable

from agente.cache.consultas import QueryResultCache
from agente.grafo.constructor import construir_grafo
from agente.grafo.plan import Plan
from agente.nodos.formatear_respuesta import formatear_respuesta
from agente.nodos.generar_cypher import (
    SAFE_DYNAMIC_QUERY_ERROR,
    GeneratedQuery,
    build_generated_query_runnable,
    correct_relationship_direction,
    generar_cypher,
    validate_generated_schema,
)
from agente.nodos.planificador import planificador
from agente.utils.db import AsyncNeo4jQueryGateway, Neo4jReadConfig
from agente.utils.prompt import build_direct_response_prompt, build_planner_prompt

SCHEMA = {
    "node_props": {
        "Empresa": [
            {"property": "id_empresa", "type": "INTEGER"},
            {"property": "nombre", "type": "STRING"},
        ],
        "Oferta_Laboral": [
            {"property": "id_ofe_laboral", "type": "INTEGER"},
            {"property": "cargo", "type": "STRING"},
        ],
    },
    "rel_props": {"PUBLICA": []},
    "relationships": [
        {"start": "Empresa", "type": "PUBLICA", "end": "Oferta_Laboral"}
    ],
}
VALID_CYPHER = (
    "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
    "WHERE e.id_empresa = $empresa_id "
    "RETURN o.cargo AS cargo LIMIT $limite"
)
CURRICULUM_SCHEMA = {
    "node_props": {
        "Carrera": [
            {"property": "id_carrera", "type": "STRING"},
            {"property": "nombre_carrera", "type": "STRING"},
        ],
        "Curso": [
            {"property": "id_curso", "type": "STRING"},
            {"property": "nombre_curso", "type": "STRING"},
        ],
    },
    "rel_props": {"ENSENIA": []},
    "relationships": [{"start": "Carrera", "type": "ENSENIA", "end": "Curso"}],
}
CURRICULUM_CYPHER = (
    "MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso) "
    "WHERE c.id_carrera = $carrera_id "
    "RETURN count(DISTINCT cu) AS total_cursos LIMIT 1"
)
MULTI_SCHEMA = {
    "node_props": {
        "Empresa": [{"property": "nombre", "type": "STRING"}],
        "Oferta_Laboral": [],
        "Requerimiento_Laboral": [],
        "Herramienta": [
            {"property": "id_herramienta", "type": "STRING"},
            {"property": "nombre_herramienta", "type": "STRING"},
        ],
    },
    "rel_props": {"PUBLICA": [], "TIENE": [], "REQUIERE": []},
    "relationships": [
        {"start": "Empresa", "type": "PUBLICA", "end": "Oferta_Laboral"},
        {"start": "Oferta_Laboral", "type": "TIENE", "end": "Requerimiento_Laboral"},
        {"start": "Requerimiento_Laboral", "type": "REQUIERE", "end": "Herramienta"},
    ],
}
MULTI_CYPHER = (
    "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
    "MATCH (o)-[:TIENE]->(r:Requerimiento_Laboral) "
    "MATCH (r)-[:REQUIERE]->(h:Herramienta) "
    "WHERE h.id_herramienta IN $herramienta_ids "
    "RETURN e.nombre AS empresa LIMIT $limite"
)


def dynamic_plan(
    parameters: dict[str, Any] | None = None, cardinality: str = "one"
) -> Plan:
    return Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Listar cargos publicados por una empresa",
        parametros=parameters or {"empresa_id": 7, "limite": 10},
        cardinality=cardinality,
    )


def schema_snapshot() -> Any:
    return SimpleNamespace(structured=SCHEMA, text="private schema", document=None)


class FakeGeneratedRunnable:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[object] = []

    async def ainvoke(self, messages: object) -> object:
        self.calls.append(messages)
        return self.output


class SequenceGeneratedRunnable:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls: list[object] = []

    async def ainvoke(self, messages: object) -> object:
        self.calls.append(messages)
        output = self.outputs[len(self.calls) - 1]
        if isinstance(output, Exception):
            raise output
        return output


class FakeGateway:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self, cypher: str, parameters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        self.calls.append((cypher, parameters))
        if self.error is not None:
            raise self.error
        return self.rows


class ExplainDriver:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls: list[object] = []

    async def execute_query(self, query: object, **kwargs: object) -> object:
        self.calls.append((query, kwargs))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakePlanner:
    def invoke(self, _: object) -> Plan:
        return dynamic_plan()


class FakeFormatter:
    async def ainvoke(self, _: object) -> object:
        return SimpleNamespace(content="La empresa publicó dos cargos.")


def test_generated_query_contract_rejects_non_json_parameters() -> None:
    with pytest.raises(ValueError):
        GeneratedQuery(cypher=VALID_CYPHER, parameters={"bad": object()})


def test_generator_loads_guide_only_during_node_and_executes_valid_query(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = importlib.import_module("agente.nodos.generar_cypher")
    guide_calls: list[str] = []
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(
            cypher=VALID_CYPHER,
            parameters={"empresa_id": 7, "limite": 10},
        )
    )
    gateway = FakeGateway([{"cargo": "Analista"}])

    def fake_guide() -> str:
        guide_calls.append("loaded")
        return "PRIVATE_GUIDE_SENTINEL"

    monkeypatch.setattr(module, "load_cypher_guide", fake_guide)
    assert guide_calls == []
    assert "PRIVATE_GUIDE_SENTINEL" not in build_planner_prompt()
    assert "PRIVATE_GUIDE_SENTINEL" not in build_direct_response_prompt()

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "¿Qué cargos publicó?", "plan": dynamic_plan()},
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=gateway,
        )
    )

    assert guide_calls == ["loaded"]
    assert gateway.calls == [
        (VALID_CYPHER, {"empresa_id": 7, "limite": 10})
    ]
    assert result == {"respuesta": "", "filas": [{"cargo": "Analista"}]}
    messages = runnable.calls[0]
    assert isinstance(messages, list)
    assert "PRIVATE_GUIDE_SENTINEL" in messages[1].content
    assert "private schema" not in messages[1].content
    assert "variables" not in result
    assert "cypher" not in result
    assert "parameters" not in result
    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines() if line]
    assert any(
        event["component"] == "dynamic_query" and event["event"] == "execution_started"
        for event in events
    )
    assert VALID_CYPHER not in output


def test_generator_resolves_dynamic_entity_candidates_before_generation() -> None:
    entity_gateway = FakeGateway(
        [{"entity_id": "CAR_7", "entity_name": "Ingeniería de Sistemas"}]
    )
    query_gateway = FakeGateway([{"total_cursos": 3}])
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(
            cypher=CURRICULUM_CYPHER,
            parameters={"carrera_id": "CAR_7"},
        )
    )
    plan = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Contar cursos de una carrera",
        parametros={"carrera": "sistemas"},
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "¿Cuántos cursos tiene sistemas?", "plan": plan},
            generated_runnable=runnable,
            schema_loader=lambda: SimpleNamespace(
                structured=CURRICULUM_SCHEMA,
                text="schema",
                document=None,
            ),
            entity_gateway=entity_gateway,
            query_gateway=query_gateway,
        )
    )

    assert result == {"respuesta": "", "filas": [{"total_cursos": 3}]}
    assert query_gateway.calls == [(CURRICULUM_CYPHER, {"carrera_id": "CAR_7"})]
    assert '"carrera_id":"CAR_7"' in str(runnable.calls[0][1].content)
    assert '"carrera":"sistemas"' not in str(runnable.calls[0][1].content)


def test_dynamic_many_resolves_all_entity_ids_and_merges_them_into_generated_query() -> None:
    entity_gateway = FakeGateway(
        [
            {"entity_id": "HER_1", "entity_name": "SAP"},
            {"entity_id": "HER_2", "entity_name": "SAP"},
        ]
    )
    query_gateway = FakeGateway([{"empresa": "Empresa A"}])
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(cypher=MULTI_CYPHER, parameters={"limite": 10})
    )
    plan = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Listar empresas relacionadas con SAP",
        parametros={"herramienta": "SAP", "limite": 10},
        cardinality="many",
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "¿Qué empresas enseñan SAP?", "plan": plan},
            generated_runnable=runnable,
            schema_loader=lambda: SimpleNamespace(
                structured=MULTI_SCHEMA, text="schema", document=None
            ),
            entity_gateway=entity_gateway,
            query_gateway=query_gateway,
        )
    )

    assert result == {
        "respuesta": "",
        "filas": [{"empresa": "Empresa A"}],
        "entity_resolution": "multiple",
    }
    assert query_gateway.calls == [
        (MULTI_CYPHER, {"herramienta_ids": ["HER_1", "HER_2"], "limite": 10})
    ]
    assert '"herramienta_ids":["HER_1","HER_2"]' in runnable.calls[0][1].content
    assert '"herramienta":"SAP"' not in runnable.calls[0][1].content


def test_dynamic_one_reports_multiple_without_selecting_an_entity() -> None:
    entity_gateway = FakeGateway(
        [
            {"entity_id": "HER_1", "entity_name": "SAP"},
            {"entity_id": "HER_2", "entity_name": "SAP"},
        ]
    )
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(cypher=MULTI_CYPHER, parameters={"limite": 10})
    )
    plan = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Consultar una herramienta específica",
        parametros={"herramienta": "SAP", "limite": 10},
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "¿Cuántas ofertas tiene SAP?", "plan": plan},
            generated_runnable=runnable,
            schema_loader=lambda: SimpleNamespace(
                structured=MULTI_SCHEMA, text="schema", document=None
            ),
            entity_gateway=entity_gateway,
            query_gateway=FakeGateway(),
        )
    )

    assert result["entity_resolution"] == "multiple"
    assert result["error"] == "entity_resolution_failed"
    assert runnable.calls == []


def test_dynamic_rejects_scalar_list_operator_mismatch_before_gateway() -> None:
    query_gateway = FakeGateway([{"empresa": "must not execute"}])
    plan = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Listar empresas",
        parametros={"herramienta": "SAP", "limite": 10},
        cardinality="many",
    )
    scalar_query = MULTI_CYPHER.replace("IN $herramienta_ids", "= $herramienta_ids")

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": plan},
            generated_runnable=FakeGeneratedRunnable(
                GeneratedQuery(cypher=scalar_query, parameters={"limite": 10})
            ),
            schema_loader=lambda: SimpleNamespace(
                structured=MULTI_SCHEMA, text="schema", document=None
            ),
            entity_gateway=FakeGateway(
                [
                    {"entity_id": "HER_1", "entity_name": "SAP"},
                    {"entity_id": "HER_2", "entity_name": "SAP"},
                ]
            ),
            query_gateway=query_gateway,
        )
    )

    assert result["error"] == "dynamic_query_failed"
    assert query_gateway.calls == []


def test_course_query_uses_only_current_entity() -> None:
    class FollowUpPlanner:
        def invoke(self, messages: object) -> Plan:
            content = str(messages[1].content)
            assert "¿Cuántas carreras de ingenieria hay?" not in content
            assert "¿Cuales son?" not in content
            return Plan(
                accion="generar_cypher",
                usar_schema=True,
                objetivo_cypher="Contar cursos de una carrera",
                parametros={"carrera": "sistemas"},
            )

    planned = planificador(
        {
            "pregunta": "¿Cuantos cursos tiene sistemas?",
        },
        planner_runnable=FollowUpPlanner(),
    )
    entity_gateway = FakeGateway(
        [{"entity_id": "CAR_7", "entity_name": "Ingeniería de Sistemas"}]
    )
    query_gateway = FakeGateway([{"total_cursos": 3}])
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(cypher=CURRICULUM_CYPHER, parameters={"carrera_id": "CAR_7"})
    )

    result = asyncio.run(
        generar_cypher(
            {
                "pregunta": "¿Cuantos cursos tiene sistemas?",
                "plan": planned["plan"],
            },
            generated_runnable=runnable,
            schema_loader=lambda: SimpleNamespace(
                structured=CURRICULUM_SCHEMA,
                text="schema",
                document=None,
            ),
            entity_gateway=entity_gateway,
            query_gateway=query_gateway,
        )
    )

    assert result == {"respuesta": "", "filas": [{"total_cursos": 3}]}
    assert query_gateway.calls[0][1] == {"carrera_id": "CAR_7"}


def test_generator_cache_hit_avoids_second_query_execution_but_not_generation() -> None:
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(
            cypher=VALID_CYPHER,
            parameters={"empresa_id": 7, "limite": 10},
        )
    )
    gateway = FakeGateway([{"cargo": "Analista"}])
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    state = {"pregunta": "consulta", "plan": dynamic_plan()}

    first = asyncio.run(
        generar_cypher(
            state,
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=gateway,
            result_cache=cache,
        )
    )
    second = asyncio.run(
        generar_cypher(
            state,
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=gateway,
            result_cache=cache,
        )
    )

    assert first == second == {"respuesta": "", "filas": [{"cargo": "Analista"}]}
    assert len(runnable.calls) == 2
    assert len(gateway.calls) == 1


def test_generator_retries_recoverable_validation_failure_with_corrective_feedback() -> None:
    invalid_cypher = "MATCH (o:Oferta) RETURN o.cargo AS cargo LIMIT 10"
    runnable = SequenceGeneratedRunnable(
        [
            GeneratedQuery(cypher=invalid_cypher, parameters={}),
            GeneratedQuery(
                cypher=VALID_CYPHER,
                parameters={"empresa_id": 7, "limite": 10},
            ),
        ]
    )
    gateway = FakeGateway([{"cargo": "Analista"}])

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=gateway,
        )
    )

    assert result == {"respuesta": "", "filas": [{"cargo": "Analista"}]}
    assert len(runnable.calls) == 2
    assert "Correction required" in runnable.calls[1][1].content
    assert gateway.calls == [(VALID_CYPHER, {"empresa_id": 7, "limite": 10})]


def test_generator_retries_explain_syntax_failure_and_executes_once_without_leaks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    malformed_cypher = (
        "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
        "WHERE e.id_empresa = $empresa_id RETURN o.cargo AS cargo BROKEN LIMIT $limite"
    )
    runnable = SequenceGeneratedRunnable(
        [
            GeneratedQuery(
                cypher=malformed_cypher,
                parameters={"empresa_id": 7, "limite": 10},
            ),
            GeneratedQuery(
                cypher=VALID_CYPHER,
                parameters={"empresa_id": 7, "limite": 10},
            ),
        ]
    )
    driver = ExplainDriver(
        [
            CypherSyntaxError("PRIVATE_EXPLAIN_ERROR"),
            SimpleNamespace(records=[], summary=SimpleNamespace(query_type="r")),
            SimpleNamespace(
                records=[SimpleNamespace(data=lambda: {"cargo": "Analista"})],
                summary=SimpleNamespace(query_type="r"),
            ),
        ]
    )
    gateway = AsyncNeo4jQueryGateway(
        driver,
        Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar"),
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=gateway,
        )
    )

    assert result == {"respuesta": "", "filas": [{"cargo": "Analista"}]}
    assert len(runnable.calls) == 2
    assert len(driver.calls) == 3
    assert [call[0].text for call in driver.calls] == [
        f"EXPLAIN {malformed_cypher}",
        f"EXPLAIN {VALID_CYPHER}",
        VALID_CYPHER,
    ]
    output = capsys.readouterr().out
    assert malformed_cypher not in output
    assert "PRIVATE_EXPLAIN_ERROR" not in output
    events = [json.loads(line) for line in output.splitlines() if line]
    retry = next(event for event in events if event["event"] == "explain_retry")
    assert retry["context"]["stage"] == "dynamic_explain"
    assert retry["context"]["attempt"] == 1
    assert retry["context"]["neo4j_code"] == "Neo.ClientError.Statement.SyntaxError"
    assert len(retry["context"]["query_fingerprint"]) == 64
    db_failure = next(
        event
        for event in events
        if event["component"] == "neo4j_query" and event["event"] == "explain_failed"
    )
    assert db_failure["context"]["stage"] == "dynamic_explain"
    assert db_failure["context"]["neo4j_category"] == "syntax"
    assert any(
        event["event"] == "attempt_started"
        and event["context"]["stage"] == "dynamic_generation"
        and event["context"]["attempt"] == 2
        for event in events
    )


@pytest.mark.parametrize(
    "failure",
    [AuthError("PRIVATE_AUTH"), ServiceUnavailable("PRIVATE_TRANSPORT")],
)
def test_generator_does_not_retry_auth_or_transport_explain_failures(
    failure: Exception,
) -> None:
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(
            cypher=VALID_CYPHER,
            parameters={"empresa_id": 7, "limite": 10},
        )
    )
    driver = ExplainDriver([failure])
    gateway = AsyncNeo4jQueryGateway(
        driver,
        Neo4jReadConfig("neo4j://unused", "reader", "secret", "ciar"),
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=gateway,
        )
    )

    assert result == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
    assert len(runnable.calls) == 1
    assert len(driver.calls) == 1


def test_corrector_changes_only_a_schema_proven_inverse_direction() -> None:
    reverse = (
        "MATCH (o:Oferta_Laboral)-[:PUBLICA]->(e:Empresa) "
        "RETURN o.cargo AS cargo LIMIT 10"
    )

    corrected = correct_relationship_direction(reverse, SCHEMA)

    assert corrected == (
        "MATCH (o:Oferta_Laboral)<-[:PUBLICA]-(e:Empresa) "
        "RETURN o.cargo AS cargo LIMIT 10"
    )
    assert correct_relationship_direction(
        "MATCH (e:Empresa)-[:INVENTADA]->(o:Oferta_Laboral) "
        "RETURN o.cargo AS cargo LIMIT 10",
        SCHEMA,
    ) == "MATCH (e:Empresa)-[:INVENTADA]->(o:Oferta_Laboral) RETURN o.cargo AS cargo LIMIT 10"


def test_corrector_cannot_make_a_write_query_executable() -> None:
    write_query = (
        "MATCH (o:Oferta_Laboral)<-[:PUBLICA]-(e:Empresa) "
        "SET o.cargo = $cargo RETURN o.cargo AS cargo LIMIT 10"
    )
    gateway = FakeGateway([{"must": "not execute"}])

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=FakeGeneratedRunnable(
                GeneratedQuery(cypher=write_query, parameters={"cargo": "secret"})
            ),
            schema_loader=schema_snapshot,
            query_gateway=gateway,
            max_generation_attempts=1,
        )
    )

    assert result == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
    assert gateway.calls == []


def test_generator_does_not_retry_terminal_query_execution_failure() -> None:
    runnable = FakeGeneratedRunnable(
        GeneratedQuery(
            cypher=VALID_CYPHER,
            parameters={"empresa_id": 7, "limite": 10},
        )
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=FakeGateway(error=RuntimeError("database unavailable")),
        )
    )

    assert result == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
    assert len(runnable.calls) == 1


def test_generator_does_not_retry_authentication_message_failure() -> None:
    runnable = SequenceGeneratedRunnable(
        [RuntimeError("authentication failed"), pytest.fail]
    )

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=runnable,
            schema_loader=schema_snapshot,
            query_gateway=FakeGateway(),
        )
    )

    assert result == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
    assert len(runnable.calls) == 1


@pytest.mark.parametrize(
    "cypher",
    [
        "MATCH (o:Oferta) RETURN o.cargo AS cargo LIMIT 10",
        "MATCH (e:Empresa)-[:INVENTADA]->(o:Oferta_Laboral) "
        "RETURN o.cargo AS cargo LIMIT 10",
        "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
        "RETURN o.titulo AS cargo LIMIT 10",
        "MATCH (e:Empresa)-[:PUBLICA]-(o:Oferta_Laboral) "
        "RETURN o.cargo AS cargo LIMIT 10",
    ],
)
def test_unknown_schema_or_unprovable_direction_is_rejected_before_database(
    cypher: str,
) -> None:
    gateway = FakeGateway([{"must": "not execute"}])

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta privada", "plan": dynamic_plan()},
            generated_runnable=FakeGeneratedRunnable(
                GeneratedQuery(cypher=cypher, parameters={})
            ),
            schema_loader=schema_snapshot,
            query_gateway=gateway,
        )
    )

    assert result == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
    assert gateway.calls == []


@pytest.mark.parametrize(
    "cypher",
    [
        "MATCH (o:Oferta_Laboral) SET o.cargo = $cargo "
        "RETURN o.cargo AS cargo LIMIT 10",
        "MATCH (o:Oferta_Laboral) RETURN o.cargo AS cargo",
    ],
)
def test_unsafe_write_or_missing_limit_is_rejected_before_database(cypher: str) -> None:
    gateway = FakeGateway([{"must": "not execute"}])
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    parameters = {"cargo": "secret"} if "$cargo" in cypher else {}

    result = asyncio.run(
        generar_cypher(
            {"pregunta": "consulta privada", "plan": dynamic_plan()},
            generated_runnable=FakeGeneratedRunnable(
                GeneratedQuery(cypher=cypher, parameters=parameters)
            ),
            schema_loader=schema_snapshot,
            query_gateway=gateway,
            result_cache=cache,
        )
    )

    assert result == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "filas": [],
        "error": "dynamic_query_failed",
    }
    assert gateway.calls == []
    assert len(cache) == 0


def test_schema_loader_is_offloaded_from_event_loop_thread() -> None:
    event_loop_thread: list[int] = []
    schema_thread: list[int] = []

    def loader() -> Any:
        schema_thread.append(threading.get_ident())
        return schema_snapshot()

    async def run() -> None:
        event_loop_thread.append(threading.get_ident())
        await generar_cypher(
            {"pregunta": "consulta", "plan": dynamic_plan()},
            generated_runnable=FakeGeneratedRunnable(
                GeneratedQuery(
                    cypher=VALID_CYPHER,
                    parameters={"empresa_id": 7, "limite": 10},
                )
            ),
            schema_loader=loader,
            query_gateway=FakeGateway([]),
        )

    asyncio.run(run())

    assert schema_thread
    assert schema_thread[0] != event_loop_thread[0]


def test_dynamic_graph_route_produces_grounded_answer() -> None:
    gateway = FakeGateway([{"cargo": "Analista"}, {"cargo": "Desarrollador"}])
    graph = construir_grafo(
        generated_runnable=FakeGeneratedRunnable(
            GeneratedQuery(
                cypher=VALID_CYPHER,
                parameters={"empresa_id": 7, "limite": 10},
            )
        ),
        schema_loader=schema_snapshot,
        cypher_gateway=gateway,
    )

    result = asyncio.run(graph.ainvoke({"pregunta": "¿Qué cargos publicó?"}))

    assert result["respuesta"] == "Encontré 2 resultados para tu consulta."
    assert result["filas"] == [{"cargo": "Analista"}, {"cargo": "Desarrollador"}]
    assert "cypher" in result
    assert "parameters" in result


def test_end_to_end_sap_multiple_entity_route_is_deterministic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    query_gateway = FakeGateway([{"empresa": "Empresa A"}, {"empresa": "Empresa B"}])
    graph = construir_grafo(
        generated_runnable=FakeGeneratedRunnable(
            GeneratedQuery(
                cypher=MULTI_CYPHER,
                parameters={"herramienta_ids": ["HER_1", "HER_2"], "limite": 10},
            )
        ),
        schema_loader=lambda: SimpleNamespace(
            structured=MULTI_SCHEMA, text="schema", document=None
        ),
        cypher_gateway=query_gateway,
    )

    result = asyncio.run(graph.ainvoke({"pregunta": "¿Qué empresas enseñan SAP?"}))

    assert result["respuesta"] == "Encontré 2 resultados para tu consulta."
    assert result["filas"] == [{"empresa": "Empresa A"}, {"empresa": "Empresa B"}]
    assert result.get("error") is None
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    assert not any(event["event"] == "skipped_after_failure" for event in events)


def test_generator_failures_and_diagnostics_do_not_leak_inputs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "private-sensitive-value"
    gateway = FakeGateway(error=RuntimeError(secret))

    result = asyncio.run(
        generar_cypher(
            {"pregunta": secret, "plan": dynamic_plan()},
            generated_runnable=FakeGeneratedRunnable(
                GeneratedQuery(
                    cypher=VALID_CYPHER,
                    parameters={"empresa_id": 7, "limite": 10},
                )
            ),
            schema_loader=schema_snapshot,
            query_gateway=gateway,
        )
    )
    formatted = asyncio.run(
        formatear_respuesta(
            {"pregunta": secret, **result},
            grounded_runnable=FakeFormatter(),
        )
    )

    output = capsys.readouterr().out
    assert formatted == {
        "respuesta": SAFE_DYNAMIC_QUERY_ERROR,
        "error": "dynamic_query_failed",
    }
    assert secret not in output
    assert secret not in formatted["respuesta"]
    events = [json.loads(line) for line in output.splitlines() if line]
    assert any(
        event["component"] == "dynamic_query" and event["event"] == "execution_started"
        for event in events
    )
    assert VALID_CYPHER not in output


def test_build_generated_runnable_uses_responses_api_and_function_calling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("agente.nodos.generar_cypher")
    model_calls: dict[str, object] = {}
    structured_calls: list[tuple[object, str]] = []
    expected = object()

    class FakeModel:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            structured_calls.append((schema, method))
            return expected

    def fake_chat_openai(**kwargs: object) -> FakeModel:
        model_calls.update(kwargs)
        return FakeModel()

    monkeypatch.setenv("OPENAI_MODEL_GENERADOR_CYPHER", "generator-test-model")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_GENERADOR_CYPHER", "high")
    monkeypatch.setenv("OPENAI_USE_RESPONSES_API_GENERADOR_CYPHER", "true")
    monkeypatch.setattr(module, "ChatOpenAI", fake_chat_openai)

    assert build_generated_query_runnable() is expected
    assert model_calls == {
        "model": "generator-test-model",
        "temperature": 0,
        "use_responses_api": True,
        "reasoning_effort": "high",
    }
    assert structured_calls == [(GeneratedQuery, "function_calling")]


def test_schema_validator_accepts_known_reverse_written_pattern() -> None:
    validate_generated_schema(
        "MATCH (o:Oferta_Laboral)<-[:PUBLICA]-(e:Empresa) "
        "RETURN o.cargo AS cargo LIMIT 10",
        SCHEMA,
    )
