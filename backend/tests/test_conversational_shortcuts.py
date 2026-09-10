from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage

import agente.grafo.constructor as constructor
import agente.nodos.orquestador as orchestrator_module
from agente.nodos.orquestador import orquestador
from agente.utils.prompt import build_orchestrator_system_prompt
from api import servidor

RESPUESTA_SALUDO = "¡Hola! ¿En qué te puedo ayudar?"
ORCHESTRATOR_PROMPT = build_orchestrator_system_prompt()


class FakeOrchestrator:
    def __init__(self, route: str, **fields: str) -> None:
        self.route = route
        self.fields = fields
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> object:
        self.calls.append(messages)
        return {"ruta": self.route, **self.fields}


class CaptureDirectResponse:
    def __init__(self) -> None:
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.calls.append(messages)
        return AIMessage(content="respuesta directa")


class FailingOrchestrator:
    async def ainvoke(self, _messages: list[BaseMessage]) -> object:
        raise RuntimeError("provider unavailable")


class StreamingGraph:
    async def astream_events(self, *_args, **_kwargs):
        yield {
            "event": "on_chat_model_stream",
            "metadata": {"langgraph_node": "redacta_respuesta"},
            "data": {"chunk": SimpleNamespace(content="Hola")},
        }
        yield {
            "event": "on_chain_end",
            "metadata": {"langgraph_node": "LangGraph"},
            "data": {"output": {"respuesta": "Hola"}},
        }


def _patch_direct_flow(monkeypatch) -> None:
    async def route_direct(_question, _prompt, **_kwargs):
        return {"ruta": "conversacion"}

    async def answer_direct(state, **_kwargs):
        return {"respuesta": RESPUESTA_SALUDO}

    def fail_cypher(*args, **kwargs):
        raise AssertionError("un saludo no debe consultar Neo4j")

    monkeypatch.setattr(constructor, "orquestador", route_direct)
    monkeypatch.setattr(constructor, "responder_directo", answer_direct)
    monkeypatch.setattr(constructor, "construye_cypher", fail_cypher)


def test_chat_saludo_no_construye_cypher(monkeypatch) -> None:
    _patch_direct_flow(monkeypatch)

    resultado = asyncio.run(constructor.responder("  ¡HÓLA!  "))

    assert resultado == RESPUESTA_SALUDO


def test_chat_stream_saludo_emite_respuesta_incremental(monkeypatch) -> None:
    _patch_direct_flow(monkeypatch)

    with TestClient(servidor.app) as client:
        response = client.post(
            "/chat/stream",
            json={"input": {"pregunta": "hola"}, "config": {}},
        )

    assert response.status_code == 200
    assert response.text.endswith("event: end\ndata: {}\n\n")
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith('data: {"respuesta":')
    ]
    assert payloads[-1]["respuesta"] == RESPUESTA_SALUDO

    values = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]
    assert any(
        value.get("type") == "progress"
        and value.get("texto") == "Entendiendo tu solicitud…"
        for value in values
    )
    assert all("pasos" not in value for value in values)
    assert all("Ruta: consulta al grafo" not in json.dumps(value) for value in values)


def test_chat_stream_emits_native_model_tokens(monkeypatch) -> None:
    monkeypatch.setattr(servidor, "construir_grafo", lambda: StreamingGraph())

    with TestClient(servidor.app) as client:
        response = client.post(
            "/chat/stream",
            json={"input": {"pregunta": "hola"}, "config": {}},
        )

    assert response.status_code == 200
    assert '"type": "progress"' in response.text
    assert "event: messages\n" in response.text
    message_payload = next(
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: [{")
    )
    assert message_payload[0]["type"] == "ai"
    assert message_payload[0]["content"] == "Hola"
    assert message_payload[1] == {"langgraph_node": "redacta_respuesta"}


def test_orchestrator_routes_capability_question_without_answering() -> None:
    runnable = FakeOrchestrator(
        "conversacion",
        pregunta_mejorada="¿Qué preguntas puedes resolver?",
    )

    result = asyncio.run(
        orquestador(
            "¿Qué preguntas puedes resolver?",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=runnable,
        )
    )

    assert result == {
        "ruta": "conversacion",
        "pregunta_mejorada": "¿Qué preguntas puedes resolver?",
    }
    assert len(runnable.calls) == 1
    assert "¿Qué preguntas puedes resolver?" in str(runnable.calls[0][1].content)


def test_orchestrator_routes_domain_question_to_guarded_graph() -> None:
    result = asyncio.run(
        orquestador(
            "¿Cuántas ofertas laborales existen?",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FakeOrchestrator(
                "cypher",
                pregunta_mejorada="¿Cuántas ofertas laborales existen?",
            ),
        )
    )

    assert result == {
        "ruta": "cypher",
        "pregunta_mejorada": "¿Cuántas ofertas laborales existen?",
    }


def test_orchestrator_corrects_conversation_route_for_schema_identity_question() -> None:
    result = asyncio.run(
        orquestador(
            "q curso ensena la profe mayhua angel",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FakeOrchestrator(
                "conversacion",
                pregunta_mejorada="¿Qué curso enseña la profesora Mayhua Ángel?",
            ),
        )
    )

    assert result == {
        "ruta": "cypher",
        "pregunta_mejorada": "¿Qué curso enseña la profesora Mayhua Ángel?",
    }


def test_orchestrator_returns_improved_question_when_intent_is_clear() -> None:
    improved = "¿Qué se puede hacer en el curso de Análisis de Algoritmos?"

    result = asyncio.run(
        orquestador(
            "q pueden hacer el curs de analis de algoritm",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FakeOrchestrator(
                "cypher",
                pregunta_mejorada=improved,
            ),
        )
    )

    assert result == {"ruta": "cypher", "pregunta_mejorada": improved}


def test_orchestrator_discards_unsafe_improved_question() -> None:
    result = asyncio.run(
        orquestador(
            "¿Cuántas ofertas laborales existen?",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FakeOrchestrator(
                "cypher",
                pregunta_mejorada="MATCH (n) RETURN n",
            ),
        )
    )

    assert result == {
        "ruta": "cypher",
        "pregunta_mejorada": "¿Cuántas ofertas laborales existen?",
    }


def test_graph_uses_improved_question_on_direct_route() -> None:
    direct = CaptureDirectResponse()
    improved = "¿Qué puedes hacer?"

    asyncio.run(
        constructor.construir_grafo(
            orchestrator_runnable=FakeOrchestrator(
                "conversacion",
                pregunta_mejorada=improved,
            ),
            direct_runnable=direct,
        ).ainvoke({"pregunta": "q puedes hacer"})
    )

    assert improved in str(direct.calls[0][1].content)


def test_orchestrator_verbose_trace_describes_input_prompt_and_output(monkeypatch) -> None:
    steps: list[tuple[str, str, object]] = []
    labels: list[tuple[str, str, object]] = []

    monkeypatch.setattr(
        orchestrator_module,
        "verbose_step",
        lambda step, description, payload=None, **_: steps.append(
            (step, description, payload)
        ),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "verbose_label",
        lambda step, label, value: labels.append((step, label, value)),
    )

    question = "¿Qué cursos enseñan SAP?"
    result = asyncio.run(
        orquestador(
            question,
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FakeOrchestrator(
                "cypher",
                pregunta_mejorada=question,
            ),
        )
    )

    assert result == {"ruta": "cypher", "pregunta_mejorada": question}
    descriptions = [description for _, description, _ in steps]
    assert descriptions == [
        "Entrada recibida",
        "Prompt enviado al modelo",
        "Respuesta del modelo",
    ]
    assert question in str(steps[0][2])
    assert "Instrucciones" in str(steps[1][2])
    assert "Ruta" in str(steps[2][2])
    assert labels[-1] == ("orquestador", "Decisión final", "Ruta: cypher")


def test_orchestrator_sends_out_of_scope_question_to_analyst() -> None:
    result = asyncio.run(
        orquestador(
            "¿Qué opinas del papa?",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FakeOrchestrator(
                "conversacion",
                pregunta_mejorada="¿Qué opinas del papa?",
            ),
        )
    )

    assert result == {
        "ruta": "conversacion",
        "pregunta_mejorada": "¿Qué opinas del papa?",
    }


def test_orchestrator_failure_degrades_to_safe_direct_analyst_route() -> None:
    result = asyncio.run(
        orquestador(
            "Hola",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FailingOrchestrator(),
        )
    )

    assert result == {"ruta": "conversacion", "pregunta_mejorada": "Hola"}


def test_orchestrator_failure_keeps_domain_question_on_graph_route() -> None:
    result = asyncio.run(
        orquestador(
            "¿Cuántas ofertas laborales existen?",
            ORCHESTRATOR_PROMPT,
            orchestrator_runnable=FailingOrchestrator(),
        )
    )

    assert result == {
        "ruta": "cypher",
        "pregunta_mejorada": "¿Cuántas ofertas laborales existen?",
    }
