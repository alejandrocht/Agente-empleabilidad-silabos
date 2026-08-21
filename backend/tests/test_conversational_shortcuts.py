from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

import agente.grafo.constructor as constructor
from agente.nodos.orquestador import orquestador
from agente.utils.conversacion import RESPUESTA_SALUDO
from api import servidor


def test_chat_saludo_no_construye_grafo(monkeypatch) -> None:
    def fail_cypher(*args, **kwargs):
        raise AssertionError("un saludo no debe consultar Neo4j")

    monkeypatch.setattr(constructor, "construye_cypher", fail_cypher)

    resultado = asyncio.run(constructor.responder("  ¡HÓLA!  "))

    assert resultado == RESPUESTA_SALUDO


def test_chat_stream_saludo_emite_respuesta_incremental(monkeypatch) -> None:
    def fail_cypher(*args, **kwargs):
        raise AssertionError("un saludo no debe construir el grafo")

    monkeypatch.setattr(constructor, "construye_cypher", fail_cypher)

    with TestClient(servidor.app) as client:
        response = client.post(
            "/chat/stream",
            json={"input": {"pregunta": "hola"}, "config": {}},
        )

    assert response.status_code == 200
    assert "Encontré" not in response.text
    assert response.text.endswith("event: end\ndata: {}\n\n")

    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith('data: {"respuesta":')
    ]
    assert payloads
    assert payloads[-1]["respuesta"] == RESPUESTA_SALUDO


def test_orchestrator_routes_capability_question_without_cypher() -> None:
    result = orquestador({"pregunta": "que preguntas puedes resolver?"})

    assert result["ruta"] == "conversacion"
    assert "carreras" in result["respuesta"]


def test_orchestrator_routes_domain_question_to_guarded_graph() -> None:
    result = orquestador({"pregunta": "¿Cuántas ofertas laborales existen?"})

    assert result == {"ruta": "cypher"}
