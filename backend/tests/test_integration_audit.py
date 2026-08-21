from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage

import agente.dashboard.servicio as dashboard_service
from agente.cache.consultas import QueryResultCache
from agente.grafo.constructor import construir_grafo
from agente.grafo.plan import Plan
from agente.nodos.generar_cypher import GeneratedQuery
from agente.nodos.inspeccionar_respuesta import SAFE_RESPONSE_INSPECTION_FALLBACK
from agente.utils.conversacion import RESPUESTA_SALUDO
from agente.utils.cypher_guard import CypherGuardError, guard_cypher
from agente.utils.neo4j_schema import Neo4jSchemaSnapshot
from api import servidor

SCHEMA = {
    "node_props": {
        "Empresa": ["id_empresa", "nombre"],
        "Oferta_Laboral": ["cargo"],
    },
    "rel_props": {"PUBLICA": []},
    "relationships": [
        {"start": "Empresa", "type": "PUBLICA", "end": "Oferta_Laboral"}
    ],
}
VALID_DYNAMIC_QUERY = (
    "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
    "WHERE e.id_empresa = $empresa_id "
    "RETURN o.cargo AS cargo LIMIT $limite"
)
WRITE_QUERY = (
    "MATCH (e:Empresa) CREATE (o:Oferta_Laboral) "
    "RETURN e.id_empresa AS id LIMIT 1"
)


def direct_plan() -> Plan:
    return Plan(accion="responder_directo")


def template_plan() -> Plan:
    return Plan(
        accion="usar_plantilla",
        template_id="resumen_general_ofertas",
        parametros={"desde": "2025-01-01", "hasta": "2025-02-01"},
    )


def dynamic_plan() -> Plan:
    return Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="List published job titles for one company",
        parametros={"empresa_id": 7, "limite": 10},
    )


class FakePlanner:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.calls = 0

    def invoke(self, _: object) -> Plan:
        self.calls += 1
        return self.plan


class FakeAsyncRunnable:
    def __init__(self, content: Any) -> None:
        self.content = content
        self.calls = 0

    async def ainvoke(self, _: list[BaseMessage]) -> BaseMessage:
        self.calls += 1
        return AIMessage(content=self.content)


class FakeGeneratedRunnable:
    def __init__(self, output: GeneratedQuery | dict[str, Any] | Exception) -> None:
        self.output = output
        self.calls = 0

    async def ainvoke(self, _: list[BaseMessage]) -> GeneratedQuery | dict[str, Any]:
        self.calls += 1
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class FakeGateway:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((cypher, dict(parameters or {})))
        return self.rows


def schema_snapshot() -> Neo4jSchemaSnapshot:
    return Neo4jSchemaSnapshot(text="", structured=SCHEMA)


def read_events(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line]


def assert_event(output: str, component: str, event: str) -> None:
    assert any(
        item["component"] == component and item["event"] == event
        for item in read_events(output)
    )


def invoke_graph(graph: Any, *, question: str) -> dict[str, Any]:
    return asyncio.run(
        graph.ainvoke(
            {"pregunta": question},
            config={
                "configurable": {
                    "user_id": "audit-user",
                    "conversation_id": "audit-conversation",
                    "thread_id": "audit-thread",
                }
            },
        )
    )


def test_greeting_uses_spanish_direct_response_without_domain_gateway(
    capsys: pytest.CaptureFixture[str],
) -> None:
    graph = construir_grafo()

    result = invoke_graph(graph, question="Hola")

    assert result["respuesta"] == RESPUESTA_SALUDO
    output = capsys.readouterr().out
    assert_event(output, "orchestrator", "route_selected")


@pytest.mark.skip(reason="Template route is no longer part of the active graph")
def test_template_route_executes_read_query_and_formats_grounded_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway = FakeGateway([{"total_ofertas": 3}])
    formatter = FakeAsyncRunnable("Se encontraron 3 ofertas.")
    graph = construir_grafo(
        planner_runnable=FakePlanner(template_plan()),
        template_gateway=gateway,
        grounded_runnable=formatter,
    )

    result = invoke_graph(graph, question="¿Cuántas ofertas hay?")

    assert result["respuesta"] == "Se encontraron 3 ofertas."
    assert result["filas"] == [{"total_ofertas": 3}]
    assert len(gateway.calls) == 1
    assert "cypher" not in result
    assert "parametros" not in result
    output = capsys.readouterr().out
    assert_event(output, "template_query", "completed")
    assert_event(output, "response_inspector", "accepted")


@pytest.mark.skip(reason="Superseded by the four-node active graph tests")
def test_dynamic_route_uses_schema_proven_query_and_public_formatter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway = FakeGateway([{"cargo": "Analista"}, {"cargo": "Desarrollador"}])
    generated = FakeGeneratedRunnable(
        GeneratedQuery(
            cypher=VALID_DYNAMIC_QUERY,
            parameters={"empresa_id": 7, "limite": 10},
        )
    )
    formatter = FakeAsyncRunnable("La empresa publicó dos cargos.")
    graph = construir_grafo(
        planner_runnable=FakePlanner(dynamic_plan()),
        generated_runnable=generated,
        schema_loader=schema_snapshot,
        cypher_gateway=gateway,
        grounded_runnable=formatter,
    )

    result = invoke_graph(graph, question="¿Qué cargos publicó?")

    assert result["respuesta"] == "La empresa publicó dos cargos."
    assert result["filas"] == [{"cargo": "Analista"}, {"cargo": "Desarrollador"}]
    assert generated.calls == 1
    assert len(gateway.calls) == 1
    assert "cypher" not in result
    output = capsys.readouterr().out
    assert_event(output, "dynamic_query", "execution_started")
    assert_event(output, "dynamic_query", "completed")


@pytest.mark.skip(reason="Superseded by the four-node active graph tests")
def test_dynamic_write_query_is_rejected_before_gateway_execution(
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway = FakeGateway([{"id": 1}])
    graph = construir_grafo(
        planner_runnable=FakePlanner(dynamic_plan()),
        generated_runnable=FakeGeneratedRunnable(
            GeneratedQuery(cypher=WRITE_QUERY, parameters={})
        ),
        schema_loader=schema_snapshot,
        cypher_gateway=gateway,
    )

    result = invoke_graph(graph, question="Create a new company")

    assert result["error"] == "dynamic_query_failed"
    assert "No pude consultar" in result["respuesta"]
    assert gateway.calls == []
    with pytest.raises(CypherGuardError):
        guard_cypher(WRITE_QUERY)
    assert_event(capsys.readouterr().out, "dynamic_query", "failed")


@pytest.mark.skip(reason="Template cache route is no longer part of the active graph")
def test_template_cache_hit_and_expiry_are_observable_at_graph_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = [0.0]
    cache = QueryResultCache(ttl_seconds=10, max_entries=4, clock=lambda: clock[0])
    gateway = FakeGateway([{"total_ofertas": 3}])
    graph = construir_grafo(
        planner_runnable=FakePlanner(template_plan()),
        template_gateway=gateway,
        grounded_runnable=FakeAsyncRunnable("Se encontraron 3 ofertas."),
        query_cache=cache,
    )

    first = invoke_graph(graph, question="¿Cuántas ofertas hay?")
    second = invoke_graph(graph, question="¿Cuántas ofertas hay?")
    clock[0] = 10.0
    third = invoke_graph(graph, question="¿Cuántas ofertas hay?")

    assert first["filas"] == second["filas"] == third["filas"]
    assert len(gateway.calls) == 2
    output = capsys.readouterr().out
    assert_event(output, "query_cache", "lookup")
    events = read_events(output)
    states = {
        event["context"].get("cache_state")
        for event in events
        if event["component"] == "query_cache"
    }
    assert {"hit", "expired"} <= states


@pytest.mark.skip(reason="Response inspector is no longer part of the active graph")
def test_response_inspector_replaces_unsafe_formatter_output(
    capsys: pytest.CaptureFixture[str],
) -> None:
    graph = construir_grafo(
        planner_runnable=FakePlanner(template_plan()),
        template_gateway=FakeGateway([{"total_ofertas": 3}]),
        grounded_runnable=FakeAsyncRunnable(
            "As an AI language model, I queried Neo4j and found 3 offers."
        ),
    )

    result = invoke_graph(graph, question="¿Cuántas ofertas hay?")

    assert result["respuesta"] == SAFE_RESPONSE_INSPECTION_FALLBACK
    assert result["error"] == "response_inspection_failed"
    assert_event(capsys.readouterr().out, "response_inspector", "rejected")


class FakeStreamGraph:
    async def astream_events(self, *_: object, **__: object) -> AsyncIterator[dict[str, Any]]:
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "planificador"},
            "data": {
                "chunk": SimpleNamespace(
                    content=[{"type": "reasoning", "text": "PRIVATE_REASONING"}]
                )
            },
        }
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "responder_directo"},
            "data": {
                "chunk": SimpleNamespace(
                    content=[{"type": "output_text", "text": "Hola, bienvenida."}]
                )
            },
        }
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {
                "output": {
                    "respuesta": "Hola, bienvenida.",
                    "cypher": "PRIVATE_CYPHER",
                    "parameters": {"secret": "PRIVATE_PARAMETER"},
                    "schema": {"secret": "PRIVATE_SCHEMA"},
                    "entidades": [{"nombre": "Carrera", "usuario_id": "PRIVATE_USER"}],
                    "filas": [{"public": True, "variables": {"private": True}}],
                }
            },
        }


class DegradedStreamGraph:
    async def astream_events(self, *_: object, **__: object) -> AsyncIterator[dict[str, Any]]:
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {
                "output": {
                    "respuesta": "No pude consultar la información de forma segura.",
                    "error": "dynamic_query_failed",
                }
            },
        }


def test_streaming_endpoint_sanitizes_internal_state_and_model_chunks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(servidor, "construir_grafo", lambda: FakeStreamGraph())

    with TestClient(servidor.app) as client:
        response = client.post(
            "/chat/stream",
            json={"input": {"pregunta": "consulta de carreras"}},
        )

    assert response.status_code == 200
    assert "Hola, bienvenida." in response.text
    assert "PRIVATE_REASONING" not in response.text
    assert "PRIVATE_CYPHER" not in response.text
    assert "PRIVATE_PARAMETER" not in response.text
    assert "PRIVATE_SCHEMA" not in response.text
    assert "PRIVATE_USER" not in response.text
    assert '"filas"' in response.text
    assert_event(capsys.readouterr().out, "api", "stream_completed")


def test_streaming_endpoint_marks_degraded_graph_completion_without_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(servidor, "construir_grafo", lambda: DegradedStreamGraph())

    with TestClient(servidor.app) as client:
        response = client.post(
            "/chat/stream",
            json={"input": {"pregunta": "consulta"}},
        )

    assert response.status_code == 200
    events = read_events(capsys.readouterr().out)
    completed = [
        event
        for event in events
        if event["component"] == "api" and event["event"] == "stream_completed"
    ]
    assert completed
    assert completed[-1]["context"]["status"] == "degraded"


def test_dashboard_endpoints_fail_closed_for_invalid_input_and_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def failing_metadata() -> dict[str, Any]:
        raise RuntimeError("PRIVATE_NEO4J_QUERY")

    monkeypatch.setattr(dashboard_service, "metadatos", failing_metadata)

    with TestClient(servidor.app) as client:
        invalid_dimension = client.get(
            "/dashboard/dimensiones/unsupported/demanda",
            params={
                "carrera_id": "CAR_demo",
                "desde": date(2025, 1, 1).isoformat(),
                "hasta": date(2025, 1, 31).isoformat(),
            },
        )
        provider_failure = client.get("/dashboard/metadata")

    assert invalid_dimension.status_code == 400
    assert "Unsupported" in invalid_dimension.json()["detail"]
    assert provider_failure.status_code == 503
    assert provider_failure.json() == {
        "detail": "Dashboard data is temporarily unavailable."
    }
    assert "PRIVATE_NEO4J_QUERY" not in provider_failure.text
    output = capsys.readouterr().out
    assert_event(output, "api", "dashboard_rejected")
    assert_event(output, "api", "dashboard_failed")
