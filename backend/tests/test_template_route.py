from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace
from typing import Any

import pytest

from agente.cache.consultas import QueryResultCache
from agente.grafo.constructor import construir_grafo
from agente.grafo.plan import Plan
from agente.nodos.ejecutar_plantilla import SAFE_QUERY_ERROR, ejecutar_plantilla
from agente.nodos.formatear_respuesta import (
    NO_CURRICULUM_RESPONSE,
    NO_RESULTS_RESPONSE,
    SAFE_FORMATTER_FALLBACK,
    UNRESOLVED_ENTITY_RESPONSE,
    build_grounded_answer_runnable,
    formatear_respuesta,
)
from agente.nodos.inspeccionar_respuesta import SAFE_RESPONSE_INSPECTION_FALLBACK
from agente.utils.cypher_guard import guard_cypher
from agente.utils.prompt import build_grounded_answer_prompt
from agente.utils.tooler import get_template, list_templates, validate_template_parameters

VALID_PARAMETERS: dict[str, Any] = {
    "desde": "2025-01-01",
    "hasta": "2025-02-01",
    "carrera_id": 7,
    "industria_id": "8",
    "empresa_id": "EMP_demo123",
    "puesto_id": "PUE_demo123",
    "limite": 25,
    "offset": 0,
    "texto": "  Python  ",
}


def template_plan(template_id: str, parameters: dict[str, Any]) -> Plan:
    return Plan(
        accion="usar_plantilla",
        usar_schema=False,
        template_id=template_id,
        parametros=parameters,
    )


def parameters_for(template_id: str) -> dict[str, Any]:
    template = get_template(template_id)
    return {name: VALID_PARAMETERS[name] for name in template.required_parameters}


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


class FakeRunnable:
    def __init__(self, content: object) -> None:
        self.content = content
        self.calls: list[object] = []

    async def ainvoke(self, messages: object) -> object:
        self.calls.append(messages)
        return type("Message", (), {"content": self.content})()


class FailingRunnable:
    async def ainvoke(self, _: object) -> object:
        raise RuntimeError("formatter failed")


class FakePlanner:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan

    def invoke(self, _: object) -> Plan:
        return self.plan


class CountingPlanner(FakePlanner):
    def __init__(self, plan: Plan) -> None:
        super().__init__(plan)
        self.calls = 0

    def invoke(self, _: object) -> Plan:
        self.calls += 1
        return super().invoke(_)


def test_complete_catalog_has_unique_bounded_read_only_templates() -> None:
    templates = list_templates()

    assert len(templates) == 20
    assert len({template.id for template in templates}) == len(templates)
    for template in templates:
        parameters = validate_template_parameters(
            template.id,
            parameters_for(template.id),
        )
        guarded = guard_cypher(template.cypher, parameters)
        assert 1 <= guarded.limit <= 100

    assert guard_cypher(
        get_template("resumen_general_ofertas").cypher,
        parameters_for("resumen_general_ofertas"),
    ).limit == 1
    assert guard_cypher(
        get_template("evolucion_mensual_ofertas").cypher,
        parameters_for("evolucion_mensual_ofertas"),
    ).limit == 100


def test_every_catalog_template_executes_through_the_fake_gateway() -> None:
    for template in list_templates():
        gateway = FakeGateway([{"template": template.id}])

        result = asyncio.run(
            ejecutar_plantilla(
                {
                    "pregunta": "Catalog test",
                    "plan": template_plan(template.id, parameters_for(template.id)),
                },
                query_gateway=gateway,
            )
        )

        assert result == {"respuesta": "", "filas": [{"template": template.id}]}
        assert len(gateway.calls) == 1


def test_template_parameters_are_sent_separately_from_cypher_text() -> None:
    gateway = FakeGateway([{"total_ofertas": 2}])

    asyncio.run(
        ejecutar_plantilla(
            {
                "pregunta": "Company offers",
                "plan": template_plan(
                    "ofertas_de_empresa",
                    {"empresa_id": "EMP_demo123"},
                ),
            },
            query_gateway=gateway,
        )
    )

    query, parameters = gateway.calls[0]
    assert "$empresa_id" in query
    assert "EMP_demo123" not in query
    assert parameters == {"empresa_id": "EMP_demo123"}


def test_executor_resolves_exact_catalog_template_and_normalizes_parameters() -> None:
    gateway = FakeGateway([{"total_ofertas": 3}])
    plan = template_plan(
        "resumen_general_ofertas",
        {"desde": "2025-01-01", "hasta": "2025-02-01"},
    )

    result = asyncio.run(
        ejecutar_plantilla(
            {"pregunta": "Resumen", "plan": plan},
            query_gateway=gateway,
        )
    )

    assert gateway.calls == [
        (
            get_template("resumen_general_ofertas").cypher,
            {"desde": "2025-01-01", "hasta": "2025-02-01"},
        )
    ]
    assert result == {"respuesta": "", "filas": [{"total_ofertas": 3}]}
    assert "cypher" not in result
    assert "parametros" not in result


def test_executor_cache_hit_avoids_second_query_execution() -> None:
    gateway = FakeGateway([{"total_ofertas": 3}])
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    state = {
        "pregunta": "Resumen",
        "plan": template_plan(
            "resumen_general_ofertas",
            {"desde": "2025-01-01", "hasta": "2025-02-01"},
        ),
    }

    first = asyncio.run(ejecutar_plantilla(state, query_gateway=gateway, result_cache=cache))
    first["filas"][0]["total_ofertas"] = 99
    second = asyncio.run(ejecutar_plantilla(state, query_gateway=gateway, result_cache=cache))

    assert len(gateway.calls) == 1
    assert second == {"respuesta": "", "filas": [{"total_ofertas": 3}]}


def test_executor_does_not_cache_query_failures() -> None:
    gateway = FakeGateway(error=RuntimeError("database unavailable"))
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    state = {
        "pregunta": "Resumen",
        "plan": template_plan(
            "resumen_general_ofertas",
            {"desde": "2025-01-01", "hasta": "2025-02-01"},
        ),
    }

    first = asyncio.run(ejecutar_plantilla(state, query_gateway=gateway, result_cache=cache))
    second = asyncio.run(ejecutar_plantilla(state, query_gateway=gateway, result_cache=cache))

    assert first["error"] == "template_query_failed"
    assert second["error"] == "template_query_failed"
    assert len(gateway.calls) == 2
    assert len(cache) == 0


def test_template_query_log_and_gateway_use_final_guarded_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = template_plan(
        "buscar_ofertas_texto",
        {
            "desde": "2025-01-01",
            "hasta": "2025-02-01",
            "texto": "  Python  ",
            "offset": 0,
            "limite": 10,
        },
    )
    template = get_template(plan.template_id or "")
    guarded = guard_cypher(
        template.cypher,
        validate_template_parameters(template.id, plan.parametros),
    )
    gateway = FakeGateway()

    asyncio.run(ejecutar_plantilla({"pregunta": "Buscar", "plan": plan}, query_gateway=gateway))

    assert gateway.calls == [(guarded.text, guarded.parameters)]
    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines() if line]
    assert any(
        event["component"] == "template_query" and event["event"] == "validated"
        for event in events
    )
    assert guarded.text not in output
    assert str(guarded.parameters) not in output


@pytest.mark.parametrize(
    "parameters",
    [
        {"desde": "2025-01-01"},
        {"desde": "invalid", "hasta": "2025-02-01"},
        {"desde": "2025-02-01", "hasta": "2025-01-01"},
    ],
)
def test_missing_or_invalid_parameters_do_not_call_database(
    parameters: dict[str, Any],
) -> None:
    gateway = FakeGateway([{"should": "not run"}])

    invalid_plan = Plan.model_construct(
        accion="usar_plantilla",
        usar_schema=False,
        template_id="resumen_general_ofertas",
        parametros=parameters,
    )
    result = asyncio.run(
        ejecutar_plantilla(
            {"pregunta": "Resumen", "plan": invalid_plan},
            query_gateway=gateway,
        )
    )

    assert gateway.calls == []
    assert result["filas"] == []
    assert result["error"] == "template_parameters_invalid"
    assert "Necesito corregir los parámetros" in result["respuesta"]


def test_gateway_error_maps_to_safe_public_answer() -> None:
    gateway = FakeGateway(error=RuntimeError("secret query failure"))

    result = asyncio.run(
        ejecutar_plantilla(
            {
                "pregunta": "Resumen",
                "plan": template_plan(
                    "resumen_general_ofertas",
                    parameters_for("resumen_general_ofertas"),
                ),
            },
            query_gateway=gateway,
        )
    )

    assert result == {
        "respuesta": SAFE_QUERY_ERROR,
        "filas": [],
        "error": "template_query_failed",
    }
    assert "secret query failure" not in result["respuesta"]

    formatter = FakeRunnable("must not be used")
    formatted = asyncio.run(
        formatear_respuesta(
            {"pregunta": "Resumen", **result},
            grounded_runnable=formatter,
        )
    )
    assert formatted == {
        "respuesta": SAFE_QUERY_ERROR,
        "error": "template_query_failed",
    }
    assert formatter.calls == []


def test_executor_enforces_catalog_bound_on_returned_rows() -> None:
    gateway = FakeGateway([{"month": index} for index in range(150)])

    result = asyncio.run(
        ejecutar_plantilla(
            {
                "pregunta": "Evolución",
                "plan": template_plan(
                    "evolucion_mensual_ofertas",
                    parameters_for("evolucion_mensual_ofertas"),
                ),
            },
            query_gateway=gateway,
        )
    )

    assert len(result["filas"]) == 100


def test_formatter_zero_rows_is_deterministic_without_model() -> None:
    runnable = FakeRunnable("must not be used")

    result = asyncio.run(
        formatear_respuesta(
            {"pregunta": "Sin datos", "filas": []},
            grounded_runnable=runnable,
        )
    )

    assert result == {"respuesta": NO_RESULTS_RESPONSE}
    assert runnable.calls == []


def test_formatter_does_not_turn_unresolved_entity_into_numeric_zero() -> None:
    runnable = FakeRunnable("La carrera tiene 0 cursos.")

    result = asyncio.run(
        formatear_respuesta(
            {
                "pregunta": "¿Cuántos cursos tiene sistemas?",
                "filas": [{"total_cursos": 0}],
                "entity_resolution": "unresolved",
            },
            grounded_runnable=runnable,
        )
    )

    assert result == {
        "respuesta": UNRESOLVED_ENTITY_RESPONSE,
        "error": "entity_resolution_failed",
    }
    assert runnable.calls == []


def test_formatter_distinguishes_no_curriculum_from_a_legitimate_zero() -> None:
    result = asyncio.run(
        formatear_respuesta(
            {
                "pregunta": "¿Cuántos cursos tiene sistemas?",
                "filas": [{"total_cursos": 0}],
                "entity_resolution": "resolved",
                "curriculum_status": "no_curriculum",
            },
            grounded_runnable=FakeRunnable("La carrera tiene 0 cursos."),
        )
    )

    assert result == {"respuesta": NO_CURRICULUM_RESPONSE}


def test_formatter_prompt_is_grounded_and_input_has_only_question_and_rows() -> None:
    runnable = FakeRunnable("Hay 3 ofertas.")
    state = {
        "pregunta": "¿Cuántas ofertas hay?",
        "filas": [{"total_ofertas": 3}],
        "plan": template_plan(
            "resumen_general_ofertas",
            parameters_for("resumen_general_ofertas"),
        ),
        "variables": {"secret": "hidden"},
    }

    result = asyncio.run(formatear_respuesta(state, grounded_runnable=runnable))

    assert result == {"respuesta": "Hay 3 ofertas."}
    messages = runnable.calls[0]
    assert isinstance(messages, list)
    assert messages[0].content == build_grounded_answer_prompt()
    assert "solamente hechos y números" in messages[0].content
    assert "No inventes" in messages[0].content
    assert "¿Cuántas ofertas hay?" in messages[1].content
    assert '"total_ofertas":3' in messages[1].content
    assert "hidden" not in messages[1].content
    assert "resumen_general_ofertas" not in messages[1].content


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ([{"type": "output_text", "text": "  Hay 1 carrera.  "}], "Hay 1 carrera."),
        (
            [
                {"type": "message", "content": [{"type": "text", "text": "Parte uno"}]},
                SimpleNamespace(type="output_text", text="Parte dos"),
            ],
            "Parte uno\nParte dos",
        ),
    ],
)
def test_formatter_normalizes_responses_api_text_blocks(
    content: object,
    expected: str,
) -> None:
    result = asyncio.run(
        formatear_respuesta(
            {"pregunta": "Cuántas carreras hay", "filas": [{"total": 1}]},
            grounded_runnable=FakeRunnable(content),
        )
    )

    assert result == {"respuesta": expected}


@pytest.mark.parametrize("content", [None, [], {"text": "unsafe"}, "   "])
def test_formatter_invalid_model_output_fails_safely(content: object) -> None:
    result = asyncio.run(
        formatear_respuesta(
            {"pregunta": "Resumen", "filas": [{"total": 1}]},
            grounded_runnable=FakeRunnable(content),
        )
    )

    assert result == {
        "respuesta": SAFE_FORMATTER_FALLBACK,
        "error": "formatter_failed",
    }


def test_formatter_model_exception_fails_safely() -> None:
    result = asyncio.run(
        formatear_respuesta(
            {"pregunta": "Resumen", "filas": [{"total": 1}]},
            grounded_runnable=FailingRunnable(),
        )
    )

    assert result == {
        "respuesta": SAFE_FORMATTER_FALLBACK,
        "error": "formatter_failed",
    }


def test_build_grounded_runnable_uses_responses_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("agente.nodos.formatear_respuesta")
    calls: dict[str, object] = {}
    expected = object()

    def fake_chat_openai(**kwargs: object) -> object:
        calls.update(kwargs)
        return expected

    monkeypatch.setenv("OPENAI_MODEL_FORMATEADOR", "formatter-test-model")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_FORMATEADOR", "high")
    monkeypatch.setenv("OPENAI_USE_RESPONSES_API_FORMATEADOR", "true")
    monkeypatch.setattr(module, "ChatOpenAI", fake_chat_openai)

    assert build_grounded_answer_runnable() is expected
    assert calls == {
        "model": "formatter-test-model",
        "temperature": 0,
        "use_responses_api": True,
        "reasoning_effort": "high",
    }


@pytest.mark.skip(reason="Template route is no longer part of the active graph")
def test_graph_template_route_produces_grounded_answer() -> None:
    plan = template_plan(
        "resumen_general_ofertas",
        parameters_for("resumen_general_ofertas"),
    )
    gateway = FakeGateway([{"total_ofertas": 3}])
    formatter = FakeRunnable("Se encontraron 3 ofertas.")
    graph = construir_grafo(
        planner_runnable=FakePlanner(plan),
        template_gateway=gateway,
        grounded_runnable=formatter,
    )

    result = asyncio.run(graph.ainvoke({"pregunta": "¿Cuántas ofertas hay?"}))

    assert result["respuesta"] == "Se encontraron 3 ofertas."
    assert result["filas"] == [{"total_ofertas": 3}]
    assert "cypher" not in result
    assert "parametros" not in result


@pytest.mark.skip(reason="Template route is no longer part of the active graph")
def test_fast_template_path_selects_and_caches_normalized_forms() -> None:
    planner = CountingPlanner(
        template_plan("listar_empresas", {}),
    )
    gateway = FakeGateway([{"total_empresas": 4}])
    cache = QueryResultCache(ttl_seconds=60, max_entries=4)
    graph = construir_grafo(
        planner_runnable=planner,
        template_gateway=gateway,
        grounded_runnable=FakeRunnable("Hay 4 empresas registradas."),
        query_cache=cache,
    )

    first = asyncio.run(
        graph.ainvoke({"pregunta": "¿CUÁNTAS EMPRESAS HAY REGISTRADAS?"})
    )
    second = asyncio.run(
        graph.ainvoke({"pregunta": "  cuantas empresas hay registradas  "})
    )

    assert first["plan"].template_id == second["plan"].template_id == "contar_empresas"
    assert first["plantilla_rapida"] is second["plantilla_rapida"] is True
    assert planner.calls == 0
    assert len(gateway.calls) == 1


@pytest.mark.skip(reason="Template route is no longer part of the active graph")
def test_fast_template_path_skips_planner_for_an_eligible_question() -> None:
    planner = CountingPlanner(template_plan("listar_empresas", {}))
    gateway = FakeGateway([{"empresa_id": "EMP_demo123", "empresa": "Demo"}])
    graph = construir_grafo(
        planner_runnable=planner,
        template_gateway=gateway,
        grounded_runnable=FakeRunnable("Encontré una empresa."),
    )

    result = asyncio.run(
        graph.ainvoke({"pregunta": "¿Cuántas ofertas publicó la empresa EMP_demo123?"})
    )

    assert result["plan"].template_id == "ofertas_de_empresa"
    assert result["plan"].parametros == {"empresa_id": "EMP_demo123"}
    assert result["plantilla_rapida"] is True
    assert planner.calls == 0
    assert len(gateway.calls) == 1


@pytest.mark.skip(reason="Legacy planner routing is no longer part of the active graph")
def test_missing_template_parameter_falls_back_to_the_current_planner() -> None:
    planner = CountingPlanner(Plan(accion="responder_directo"))
    graph = construir_grafo(
        planner_runnable=planner,
        direct_runnable=FakeRunnable("Necesito el identificador de la empresa."),
    )

    result = asyncio.run(
        graph.ainvoke({"pregunta": "¿Cuántas ofertas publicó la empresa?"})
    )

    assert result["plantilla_rapida"] is False
    assert planner.calls == 1
    assert result["respuesta"] == "Necesito el identificador de la empresa."


@pytest.mark.skip(reason="Legacy planner routing is no longer part of the active graph")
def test_arbitrary_question_keeps_current_planner_behavior() -> None:
    planner = CountingPlanner(Plan(accion="responder_directo"))
    graph = construir_grafo(
        planner_runnable=planner,
        direct_runnable=FakeRunnable("Respuesta del planner."),
    )

    result = asyncio.run(graph.ainvoke({"pregunta": "Explícame cómo usar el agente."}))

    assert result["plantilla_rapida"] is False
    assert planner.calls == 1
    assert result["respuesta"] == "Respuesta del planner."


@pytest.mark.skip(reason="Response inspector is no longer part of the active graph")
def test_graph_inspector_replaces_invalid_grounded_response() -> None:
    plan = template_plan(
        "resumen_general_ofertas",
        parameters_for("resumen_general_ofertas"),
    )
    graph = construir_grafo(
        planner_runnable=FakePlanner(plan),
        template_gateway=FakeGateway([{"total_ofertas": 3}]),
        grounded_runnable=FakeRunnable("As an AI language model, I queried Neo4j."),
    )

    result = asyncio.run(graph.ainvoke({"pregunta": "¿Cuántas ofertas hay?"}))

    assert result["respuesta"] == SAFE_RESPONSE_INSPECTION_FALLBACK
    assert result["error"] == "response_inspection_failed"
    assert "reason" not in result


def test_diagnostics_do_not_expose_query_inputs_or_results(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "private-sensitive-value"
    gateway = FakeGateway([{"descripcion": secret}])
    plan = template_plan(
        "buscar_ofertas_texto",
        {
            "desde": "2025-01-01",
            "hasta": "2025-02-01",
            "texto": "analista",
            "offset": 0,
            "limite": 10,
        },
    )
    formatter = FakeRunnable(secret)

    rows = asyncio.run(
        ejecutar_plantilla(
            {"pregunta": secret, "plan": plan},
            query_gateway=gateway,
        )
    )
    asyncio.run(
        formatear_respuesta(
            {"pregunta": secret, **rows},
            grounded_runnable=formatter,
        )
    )

    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines() if line]
    assert any(
        event["component"] == "template_query" and event["event"] == "completed"
        for event in events
    )
    assert secret not in output
    assert "MATCH" not in output
