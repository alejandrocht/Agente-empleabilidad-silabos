from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
from langchain_core.messages import BaseMessage

import agente.grafo.constructor as constructor
from agente.nodos.orquestador import orquestador
from api import servidor

RESPUESTA_SALUDO = "¡Hola! ¿En qué te puedo ayudar?"


class FakeOrchestrator:
    def __init__(self, route: str) -> None:
        self.route = route
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> object:
        self.calls.append(messages)
        return {"ruta": self.route}


class FailingOrchestrator:
    async def ainvoke(self, _messages: list[BaseMessage]) -> object:
        raise RuntimeError("provider unavailable")


def _patch_direct_flow(monkeypatch) -> None:
    async def route_direct(state, **_kwargs):
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


def test_orchestrator_routes_capability_question_without_answering() -> None:
    runnable = FakeOrchestrator("conversacion")

    result = asyncio.run(
        orquestador(
            {"pregunta": "¿Qué preguntas puedes resolver?"},
            orchestrator_runnable=runnable,
        )
    )

    assert result == {"ruta": "conversacion"}
    assert len(runnable.calls) == 1
    assert "¿Qué preguntas puedes resolver?" in str(runnable.calls[0][1].content)


def test_orchestrator_routes_domain_question_to_guarded_graph() -> None:
    result = asyncio.run(
        orquestador(
            {"pregunta": "¿Cuántas ofertas laborales existen?"},
            orchestrator_runnable=FakeOrchestrator("cypher"),
        )
    )

    assert result == {"ruta": "cypher"}


def test_orchestrator_sends_out_of_scope_question_to_analyst() -> None:
    result = asyncio.run(
        orquestador(
            {"pregunta": "¿Qué opinas del papa?"},
            orchestrator_runnable=FakeOrchestrator("conversacion"),
        )
    )

    assert result == {"ruta": "conversacion"}


def test_orchestrator_failure_degrades_to_safe_direct_analyst_route() -> None:
    result = asyncio.run(
        orquestador(
            {"pregunta": "Hola"},
            orchestrator_runnable=FailingOrchestrator(),
        )
    )

    assert result == {"ruta": "conversacion"}


def test_orchestrator_failure_keeps_domain_question_on_graph_route() -> None:
    result = asyncio.run(
        orquestador(
            {"pregunta": "¿Cuántas ofertas laborales existen?"},
            orchestrator_runnable=FailingOrchestrator(),
        )
    )

    assert result == {"ruta": "cypher"}
