from __future__ import annotations

import asyncio
import importlib
import json

import pytest
from pydantic import ValidationError

from agente.grafo import constructor
from agente.grafo.plan import Plan
from agente.nodos.obtiene_pregunta import MAX_PREGUNTA_LOG_CHARS, obtiene_pregunta
from agente.nodos.planificador import build_planner_runnable, planificador
from agente.utils.prompt import build_planner_prompt
from agente.utils.tooler import list_templates


def parse_logs(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line]


def test_plan_directo_aplica_valores_estrictos_omitidos() -> None:
    plan = Plan.model_validate({"accion": "responder_directo"})

    assert plan.accion == "responder_directo"
    assert plan.usar_schema is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"template_id": "resumen_general_ofertas"},
        {"objetivo_cypher": "Contar ofertas"},
        {"usar_schema": True},
    ],
)
def test_responder_directo_rechaza_campos_exclusivos(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Plan.model_validate({"accion": "responder_directo", **overrides})


def test_usar_plantilla_rechaza_parametros_incompletos() -> None:
    with pytest.raises(ValidationError, match="parámetros completos"):
        Plan(
            accion="usar_plantilla",
            template_id="resumen_general_ofertas",
            parametros={"desde": "2025-01-01"},
        )


def test_usar_plantilla_acepta_id_del_catalogo_y_parametros_completos() -> None:
    plan = Plan(
        accion="usar_plantilla",
        template_id="resumen_general_ofertas",
        parametros={"desde": "2025-01-01", "hasta": "2025-02-01"},
    )

    assert plan.parametros == {"desde": "2025-01-01", "hasta": "2025-02-01"}


def test_generar_cypher_exige_schema_y_normaliza_objetivo() -> None:
    plan = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="  Contar ofertas por carrera  ",
    )

    assert plan.objetivo_cypher == "Contar ofertas por carrera"


@pytest.mark.parametrize("action", ["responder_directo", "usar_plantilla", "generar_cypher"])
@pytest.mark.skip(reason="Legacy planner routing is no longer part of the active graph")
def test_enrutar_plan_usa_una_tabla_para_las_tres_acciones(action: str) -> None:
    values: dict[str, object] = {"accion": action}
    if action == "usar_plantilla":
        values.update(
            template_id="resumen_general_ofertas",
            parametros={"desde": "2025-01-01", "hasta": "2025-02-01"},
        )
    elif action == "generar_cypher":
        values.update(usar_schema=True, objetivo_cypher="Contar ofertas")

    assert constructor.enrutar_plan({"plan": Plan(**values)}) == action


@pytest.mark.skip(reason="Legacy planner routing is no longer part of the active graph")
def test_enrutar_error_termina_en_inspeccion() -> None:
    assert constructor.enrutar_plan({"error": "planner_failed"}) == "inspeccionar_respuesta"


def test_prompt_expone_solo_metadatos_del_catalogo() -> None:
    prompt = build_planner_prompt()
    for template in list_templates():
        assert template.id in prompt
        assert template.description in prompt
        assert ", ".join(template.required_parameters) in prompt
        assert template.cypher not in prompt
    assert "MATCH (" not in prompt


def test_prompt_requires_structured_entity_candidates() -> None:
    prompt = build_planner_prompt()

    assert '`{"carrera":"sistemas"}`' in prompt
    assert '`{"count":0}`' in prompt
    assert "Do not invent or emit Silabo, Cobertura" in prompt


def test_build_planner_runnable_uses_structured_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner_module = importlib.import_module("agente.nodos.planificador")
    calls: dict[str, object] = {}
    structured_runnable = object()

    class FakeModel:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            calls["schema"] = schema
            calls["method"] = method
            return structured_runnable

    monkeypatch.setenv("OPENAI_MODEL_PLANIFICADOR", "planner-test-model")
    def fake_chat_openai(**kwargs: object) -> FakeModel:
        calls.update(kwargs)
        return FakeModel()

    monkeypatch.setattr(planner_module, "ChatOpenAI", fake_chat_openai)

    assert build_planner_runnable() is structured_runnable
    assert calls["model"] == "planner-test-model"
    assert calls["schema"] is Plan
    assert calls["method"] == "function_calling"


def test_planificador_usa_runnable_estructurado_aislado() -> None:
    expected = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Comparar ofertas por carrera",
    )

    class FakeStructuredRunnable:
        messages: list[object] | None = None

        def invoke(self, messages: list[object]) -> Plan:
            self.messages = messages
            return expected

    fake = FakeStructuredRunnable()
    result = planificador(
        {"pregunta": "Compara las ofertas por carrera"},
        planner_runnable=fake,
    )

    assert result["plan"] == expected
    assert fake.messages is not None
    assert "Compara las ofertas por carrera" in fake.messages[1].content


def test_planificador_no_recibe_estado_de_otros_turnos() -> None:
    class Planner:
        def invoke(self, messages: list[object]) -> Plan:
            content = str(messages[1].content)
            assert "previous answer" not in content
            return Plan(accion="responder_directo")

    result = planificador({"pregunta": "Hola"}, planner_runnable=Planner())

    assert result["plan"].accion == "responder_directo"


@pytest.mark.skip(reason="Legacy planner routing is no longer part of the active graph")
def test_new_question_clears_previous_error_before_dynamic_route() -> None:
    plan = Plan(
        accion="generar_cypher",
        usar_schema=True,
        objetivo_cypher="Listar carreras de ingeniería",
    )
    restored_state = {"pregunta": "¿Cuáles son de ingeniería?", "error": "old_failure"}

    question_update = obtiene_pregunta(restored_state)
    current_state = {**restored_state, **question_update, "plan": plan}

    assert current_state["error"] is None
    assert constructor.enrutar_plan(current_state) == "generar_cypher"


def test_planificador_marca_fallo_si_el_modelo_no_devuelve_un_plan() -> None:
    class InvalidPlanner:
        def invoke(self, _: object) -> object:
            return {"accion": "respuesta_inexistente"}

    result = planificador({"pregunta": "consulta"}, planner_runnable=InvalidPlanner())

    assert result == {
        "respuesta": "No pude interpretar la consulta de forma segura.",
        "error": "planner_failed",
    }


def test_planificador_diagnostica_validacion_sin_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class InvalidPlanner:
        def invoke(self, _: object) -> object:
            return {"accion": "responder_directo", "usar_schema": "no es un booleano"}

    result = planificador(
        {"pregunta": "pregunta privada que no debe aparecer"},
        planner_runnable=InvalidPlanner(),
    )

    events = parse_logs(capsys.readouterr().out)
    validation_event = next(event for event in events if event["event"] == "validation_failed")
    assert validation_event["context"]["error_type"] == "ValidationError"
    assert "pregunta privada" not in json.dumps(events)
    assert result["error"] == "planner_failed"


def test_grafo_se_compila_sin_checkpointer_y_con_barreras_de_seguridad() -> None:
    graph = constructor.construir_grafo()
    node_names = set(graph.get_graph().nodes)
    expected_nodes = {
        "__start__",
        "__end__",
        "obtiene_pregunta",
        "prompt_injection",
        "contextualiza_pregunta",
        "contextualized_prompt_injection",
        "orquestador",
        "obtiene_schema",
        "construye_cypher",
        "resuelve_entidades",
        "cypher_guard",
        "devuelve_respuesta",
        "guarda_memoria_corta",
        "responder_directo",
    }

    assert getattr(graph, "checkpointer", None) is None
    assert node_names == expected_nodes
    assert {
        (edge.source, edge.target)
        for edge in graph.get_graph().edges
    } == {
        ("__start__", "obtiene_pregunta"),
            ("obtiene_pregunta", "prompt_injection"),
            ("prompt_injection", "contextualiza_pregunta"),
            ("contextualiza_pregunta", "contextualized_prompt_injection"),
        ("contextualized_prompt_injection", "orquestador"),
        ("orquestador", "guarda_memoria_corta"),
        ("orquestador", "obtiene_schema"),
        ("orquestador", "responder_directo"),
        ("obtiene_schema", "construye_cypher"),
        ("construye_cypher", "resuelve_entidades"),
        ("resuelve_entidades", "cypher_guard"),
        ("cypher_guard", "devuelve_respuesta"),
        ("devuelve_respuesta", "guarda_memoria_corta"),
        ("guarda_memoria_corta", "__end__"),
        ("responder_directo", "guarda_memoria_corta"),
    }


def test_grafo_rechaza_pregunta_fuera_del_alcance_sin_llamar_al_modelo() -> None:
    class Direct:
        calls = 0

        async def ainvoke(self, _: object) -> object:
            self.calls += 1
            return type("Message", (), {"content": "Respuesta directa válida para CIAR."})()

    direct = Direct()
    result = asyncio.run(
        constructor.construir_grafo(
            direct_runnable=direct,
        ).ainvoke({"pregunta": "¿Cuál es la capital de Perú?"})
    )

    assert result["respuesta"] != "Respuesta directa válida para CIAR."
    assert result["ruta"] == "finalizar"
    assert result["error"] == "fuera_de_alcance"
    assert direct.calls == 0


def test_obtiene_pregunta_loguea_solo_longitud(
    capsys: pytest.CaptureFixture[str],
) -> None:
    pregunta = "x" * MAX_PREGUNTA_LOG_CHARS + "NO_DEBE_APARECER"

    result = obtiene_pregunta({"pregunta": pregunta})

    output = capsys.readouterr().out
    assert result == {"pregunta": pregunta, "error": None}
    assert any(event["context"].get("length") == len(pregunta) for event in parse_logs(output))
    assert "NO_DEBE_APARECER" not in output
