from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from agente.grafo.constructor import responder
from agente.utils.validacion import MAX_PREGUNTA_CHARS, EntradaInvalida, validar_pregunta
from api import servidor


def test_question_length_boundary_is_inclusive() -> None:
    question = "x" * MAX_PREGUNTA_CHARS

    assert validar_pregunta(question) == question
    with pytest.raises(EntradaInvalida, match=str(MAX_PREGUNTA_CHARS)):
        validar_pregunta(question + "x")


@pytest.mark.parametrize("value", [None, 123, {}, []])
def test_non_text_question_is_rejected(value: object) -> None:
    with pytest.raises(EntradaInvalida, match="texto"):
        validar_pregunta(value)


@pytest.mark.parametrize(
    "question",
    [
        "MATCH (n) DETACH DELETE n",
        "RETURN 1",
        "PROFILE MATCH (n) RETURN n",
    ],
)
def test_clause_led_cypher_is_rejected_before_the_graph(question: str) -> None:
    with pytest.raises(EntradaInvalida) as caught:
        validar_pregunta(question)

    assert caught.value.tipo == "cypher_injection"


def test_responder_defers_validation_to_the_graph_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agente.grafo.constructor as constructor

    received: dict[str, object] = {}

    class FakeGraph:
        async def ainvoke(self, state: dict[str, object], *, config: object) -> dict[str, object]:
            received.update(state)
            return {"respuesta": "safe response"}

    def build_graph() -> FakeGraph:
        return FakeGraph()

    monkeypatch.setattr(constructor, "construir_grafo", build_graph)

    response = asyncio.run(responder("x" * (MAX_PREGUNTA_CHARS + 1)))

    assert response == "safe response"
    assert received["pregunta"] == "x" * (MAX_PREGUNTA_CHARS + 1)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/chat", {"pregunta": "x" * (MAX_PREGUNTA_CHARS + 1)}),
        ("/preguntar", {"texto": "x" * (MAX_PREGUNTA_CHARS + 1)}),
        ("/chat/stream", {"input": {"pregunta": "x" * (MAX_PREGUNTA_CHARS + 1)}}),
        ("/chat/stream", {"input": {}}),
    ],
)
def test_public_endpoints_return_bad_request_without_running_work(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, object],
) -> None:
    async def fail_if_called(*_: object, **__: object) -> str:
        raise AssertionError("invalid input reached the graph")

    monkeypatch.setattr(servidor, "responder", fail_if_called)

    with TestClient(servidor.app) as client:
        response = client.post(path, json=body)

    assert response.status_code == 400
    assert response.json()["detail"]
