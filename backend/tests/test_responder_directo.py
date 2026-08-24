from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from contextlib import suppress
from types import SimpleNamespace

import pytest

from agente.grafo.constructor import construir_grafo
from agente.grafo.plan import Plan
from agente.nodos.inspeccionar_respuesta import SAFE_RESPONSE_INSPECTION_FALLBACK
from agente.nodos.responder_directo import (
    SAFE_RESPONSE_FALLBACK,
    build_direct_response_runnable,
    responder_directo,
)
from agente.utils.prompt import build_direct_response_prompt
from agente.utils.response_inspector import inspect_response


def direct_plan() -> Plan:
    return Plan(
        accion="responder_directo",
        usar_schema=False,
    )


class FakeAsyncRunnable:
    def __init__(self, content: object) -> None:
        self.content = content
        self.messages: object | None = None

    async def ainvoke(self, messages: object) -> object:
        self.messages = messages
        return type("Message", (), {"content": self.content})()


class NeverEndingRunnable:
    async def ainvoke(self, _: object) -> object:
        await asyncio.Future()
        return type("Message", (), {"content": "nunca"})()


class FakePlanner:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan

    def invoke(self, _: object) -> Plan:
        return self.plan


def test_responder_directo_devuelve_respuesta_string() -> None:
    runnable = FakeAsyncRunnable("  Hola, ¿en qué te ayudo?  ")

    result = asyncio.run(
        responder_directo(
            {"pregunta": "Hola", "plan": direct_plan()},
            direct_runnable=runnable,
        )
    )

    assert result == {"respuesta": "Hola, ¿en qué te ayudo?"}


@pytest.mark.parametrize(
    "response",
    [
        "",
        "too short",
        "x" * 2_001,
        "Respuesta con 字 inesperado.",
        "The company has 3 offers available.",
        "As an AI language model, I queried Neo4j and found 10 offers.",
    ],
)
def test_response_inspector_rejects_obvious_invalid_outputs(response: str) -> None:
    valid, _ = inspect_response(response)

    assert valid is False


@pytest.mark.skip(reason="Response inspection is not part of the active graph")
def test_graph_inspector_replaces_invalid_direct_response_at_public_boundary() -> None:
    graph = construir_grafo(
        planner_runnable=FakePlanner(direct_plan()),
        direct_runnable=FakeAsyncRunnable("The company has 3 offers available."),
    )

    result = asyncio.run(graph.ainvoke({"pregunta": "Hola"}))

    assert result["respuesta"] == SAFE_RESPONSE_INSPECTION_FALLBACK
    assert result["error"] == "response_inspection_failed"
    assert "reason" not in result


def test_responder_directo_incluye_solo_la_pregunta() -> None:
    runnable = FakeAsyncRunnable("ok")
    state = {
        "pregunta": "¿Qué datos hay?",
        "plan": direct_plan(),
        "variables": {"schema": "prohibido"},
    }

    asyncio.run(responder_directo(state, direct_runnable=runnable))

    assert isinstance(runnable.messages, list)
    assert runnable.messages[0].content == build_direct_response_prompt()
    user_content = runnable.messages[1].content
    assert "¿Qué datos hay?" in user_content
    assert "contexto" not in user_content.lower()
    assert "schema" not in user_content


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ([{"type": "text", "text": "  primera  "}], "primera"),
        (
            [
                {"type": "output_text", "text": "primera"},
                {"type": "text", "text": "segunda"},
            ],
            "primera\nsegunda",
        ),
        (
            [{"type": "message", "content": [{"type": "text", "text": "anidada"}]}],
            "anidada",
        ),
        ([SimpleNamespace(type="output_text", text="objeto")], "objeto"),
    ],
)
def test_responder_directo_normaliza_bloques_de_texto(
    content: object, expected: str
) -> None:
    result = asyncio.run(
        responder_directo(
            {"pregunta": "Hola", "plan": direct_plan()},
            direct_runnable=FakeAsyncRunnable(content),
        )
    )

    assert result == {"respuesta": expected}


@pytest.mark.parametrize(
    "content",
    [None, {"text": "sin tipo"}, [{"type": "image_url", "url": "ignored"}], "   ", []],
)
def test_responder_directo_usa_fallback_para_contenido_vacio_o_invalido(
    content: object,
) -> None:
    result = asyncio.run(
        responder_directo(
            {"pregunta": "Hola", "plan": direct_plan()},
            direct_runnable=FakeAsyncRunnable(content),
        )
    )

    assert result == {
        "respuesta": SAFE_RESPONSE_FALLBACK,
        "error": "direct_response_failed",
    }


def test_responder_directo_no_deja_la_solicitud_abierta_si_el_modelo_no_responde(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CIAR_DIRECT_RESPONSE_TIMEOUT_SECONDS", "0.01")

    async def invoke_with_deadline() -> object:
        task = asyncio.create_task(
            responder_directo(
                {"pregunta": "¿Qué opinas del papa?"},
                direct_runnable=NeverEndingRunnable(),
            )
        )
        done, _ = await asyncio.wait({task}, timeout=0.1)
        if not done:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            return None
        return task.result()

    result = asyncio.run(invoke_with_deadline())

    assert result == {
        "respuesta": SAFE_RESPONSE_FALLBACK,
        "error": "direct_response_timeout",
    }


def test_responder_directo_no_importa_recursos_de_consulta() -> None:
    module = importlib.import_module("agente.nodos.responder_directo")
    source = inspect.getsource(module)

    assert "agente.utils.db" not in source
    assert "neo4j_schema" not in source
    assert "guia_creacion_querys_cypher" not in source
    assert "agente.utils.tooler" not in source
    assert ".bind_tools(" not in source


def test_prompt_directo_declara_limites_de_datos() -> None:
    prompt = build_direct_response_prompt()
    normalized_prompt = " ".join(prompt.split())

    assert "saludos" in prompt
    assert "no requieren consultar la base de datos" in normalized_prompt
    assert "No afirmes hechos actuales del grafo" in prompt
    assert "no" in prompt.lower() and "inventes datos académicos" in prompt


@pytest.mark.parametrize(
    ("direct_model", "direct_effort", "expected_model", "expected_effort"),
    [
        ("direct-test-model", None, "direct-test-model", None),
        (None, "high", "shared-test-model", "high"),
    ],
)
def test_build_direct_response_runnable_uses_responses_api_by_default_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
    direct_model: str | None,
    direct_effort: str | None,
    expected_model: str,
    expected_effort: str | None,
) -> None:
    module = importlib.import_module("agente.nodos.responder_directo")
    calls: dict[str, object] = {}
    expected = object()

    def fake_chat_openai(**kwargs: object) -> object:
        calls.update(kwargs)
        return expected

    monkeypatch.setenv("OPENAI_MODEL", "shared-test-model")
    monkeypatch.delenv("OPENAI_USE_RESPONSES_API_RESPONDER_DIRECTO", raising=False)
    if direct_model is None:
        monkeypatch.delenv("OPENAI_MODEL_RESPONDER_DIRECTO", raising=False)
    else:
        monkeypatch.setenv("OPENAI_MODEL_RESPONDER_DIRECTO", direct_model)
    if direct_effort is None:
        monkeypatch.delenv("OPENAI_REASONING_EFFORT_RESPONDER_DIRECTO", raising=False)
    else:
        monkeypatch.setenv("OPENAI_REASONING_EFFORT_RESPONDER_DIRECTO", direct_effort)
    monkeypatch.setattr(module, "ChatOpenAI", fake_chat_openai)

    assert build_direct_response_runnable() is expected
    expected_calls: dict[str, object] = {
        "model": expected_model,
        "temperature": 0,
        "use_responses_api": True,
    }
    if expected_effort is not None:
        expected_calls["reasoning_effort"] = expected_effort
    assert calls == expected_calls


def test_diagnosticos_no_exponen_contenido_ni_secretos(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "sk-private-secret"
    question = "pregunta privada"
    answer = "respuesta privada"

    asyncio.run(
        responder_directo(
            {"pregunta": question, "plan": direct_plan()},
            direct_runnable=FakeAsyncRunnable(answer),
        )
    )

    output = capsys.readouterr().out
    events = [json.loads(line) for line in output.splitlines() if line]
    assert any(event["event"] == "started" for event in events)
    assert any(
        event["event"] == "completed" and event["context"].get("length") == len(answer)
        for event in events
    )
    assert question not in output
    assert answer not in output
    assert secret not in output
