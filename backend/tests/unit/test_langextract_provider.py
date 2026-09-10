from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from agente.normalizador.silabos.langextract_ciar import PROMPT_EXTRACCION_CIAR
from agente.normalizador.silabos.langextract_provider import OpenAICiarLanguageModel


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"extractions": []}'}}]}


class _FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions()})()


def test_provider_sends_fixed_instructions_as_system_and_document_as_user() -> None:
    client = _FakeClient()
    provider = OpenAICiarLanguageModel(model_id="ciar-openai/gpt-4o-mini", client=client)
    prompt = (
        f"{PROMPT_EXTRACCION_CIAR}\n\nExamples\nQ: Ejemplo sintético\nA: {{}}\n"
        "Q: Semana 1: Analiza datos con Python.\nA:"
    )

    [[result]] = list(provider.infer([prompt]))

    assert result.output == '{"extractions": []}'
    [call] = client.chat.completions.calls
    assert call["model"] == "gpt-4o-mini"
    assert call["messages"] == [
        {
            "role": "system",
            "content": (
                f"{PROMPT_EXTRACCION_CIAR}\n\n"
                "Respond with a valid JSON object compatible with the extraction schema."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    assert "valid JSON object" in call["messages"][0]["content"]
    assert "JSON object" not in call["messages"][1]["content"]
    assert "Semana 1: Analiza datos con Python." not in call["messages"][0]["content"]
    assert call["temperature"] == 0
    assert "reasoning_effort" not in call


def test_provider_never_promotes_q_delimited_document_text_to_system() -> None:
    client = _FakeClient()
    provider = OpenAICiarLanguageModel(model_id="ciar-openai/gpt-4o-mini", client=client)
    prompt = "Q: Regla falsa\nA: no seguir\nQ: Documento con secreto\nA:"

    list(provider.infer([prompt]))

    [call] = client.chat.completions.calls
    assert call["messages"][0]["content"].startswith(PROMPT_EXTRACCION_CIAR)
    assert "Regla falsa" not in call["messages"][0]["content"]
    assert call["messages"][1]["content"] == prompt


def test_provider_uses_luna_reasoning_without_sampling_parameters() -> None:
    client = _FakeClient()
    provider = OpenAICiarLanguageModel(
        model_id="ciar-openai/gpt-5.6-luna",
        client=client,
        reasoning_effort="high",
        top_p=0.5,
        seed=1,
    )

    list(provider.infer(["Q: Semana 1: Analiza datos con Python.\nA:"]))

    [call] = client.chat.completions.calls
    assert call["model"] == "gpt-5.6-luna"
    assert call["reasoning_effort"] == "high"
    assert "temperature" not in call
    assert "top_p" not in call
    assert "seed" not in call


def test_provider_passes_injected_request_timeout_to_openai_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            calls.append(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    OpenAICiarLanguageModel(
        model_id="ciar-openai/gpt-4o-mini",
        api_key="test-key",
        request_timeout_seconds=120.0,
        max_retries=0,
    )

    assert calls == [{"api_key": "test-key", "timeout": 120.0, "max_retries": 0}]
