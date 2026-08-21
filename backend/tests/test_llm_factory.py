from __future__ import annotations

from typing import Any

import pytest

import agente.utils.llm as llm
from agente.utils.llm import (
    DIRECT_RESPONSE_CHAT_PROFILE,
    build_chat_openai,
)


def test_role_profile_uses_responses_api_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.update(kwargs)
        return object()

    monkeypatch.delenv("OPENAI_MODEL_RESPONDER_DIRECTO", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.delenv("OPENAI_REASONING_EFFORT_RESPONDER_DIRECTO", raising=False)
    monkeypatch.delenv("OPENAI_USE_RESPONSES_API_RESPONDER_DIRECTO", raising=False)

    build_chat_openai(DIRECT_RESPONSE_CHAT_PROFILE, constructor=fake_chat_openai)

    assert calls == {
        "model": "shared-model",
        "temperature": 0,
        "use_responses_api": True,
    }


def test_role_profile_allows_opt_out_of_responses_api_and_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.update(kwargs)
        return object()

    monkeypatch.setenv("OPENAI_MODEL_RESPONDER_DIRECTO", "direct-model")
    monkeypatch.delenv("OPENAI_REASONING_EFFORT_RESPONDER_DIRECTO", raising=False)
    monkeypatch.setenv("OPENAI_USE_RESPONSES_API_RESPONDER_DIRECTO", "false")

    build_chat_openai(DIRECT_RESPONSE_CHAT_PROFILE, constructor=fake_chat_openai)

    assert calls == {
        "model": "direct-model",
        "temperature": 0,
        "use_responses_api": False,
    }


def test_role_profile_passes_reasoning_effort_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.update(kwargs)
        return object()

    monkeypatch.setenv("OPENAI_MODEL_RESPONDER_DIRECTO", "direct-model")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_RESPONDER_DIRECTO", "max")

    build_chat_openai(DIRECT_RESPONSE_CHAT_PROFILE, constructor=fake_chat_openai)

    assert calls == {
        "model": "direct-model",
        "temperature": 0,
        "use_responses_api": True,
        "reasoning_effort": "max",
    }


def test_factory_uses_its_runtime_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(llm, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setenv("OPENAI_MODEL_RESPONDER_DIRECTO", "direct-model")

    build_chat_openai(DIRECT_RESPONSE_CHAT_PROFILE)

    assert calls[0]["model"] == "direct-model"
