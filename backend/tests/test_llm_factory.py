from __future__ import annotations

from typing import Any

import pytest

import agente.utils.llm as llm
from agente.utils.llm import (
    ANALYST_CHAT_PROFILE,
    GENERATED_QUERY_CHAT_PROFILE,
    ORCHESTRATOR_CHAT_PROFILE,
    build_chat_openai,
)


@pytest.mark.parametrize(
    ("profile", "model_env", "model", "reasoning_effort"),
    [
        (ORCHESTRATOR_CHAT_PROFILE, "OPENAI_MODEL_ORQUESTADOR", "gpt-oss-120b", None),
        (
            GENERATED_QUERY_CHAT_PROFILE,
            "OPENAI_MODEL_GENERADOR_CYPHER",
            "gpt-5.6-luna",
            "max",
        ),
        (ANALYST_CHAT_PROFILE, "OPENAI_MODEL_ANALISTA", "gpt-oss-20b", None),
    ],
)
def test_conversational_roles_use_explicit_models_and_responses_api(
    monkeypatch: pytest.MonkeyPatch,
    profile: object,
    model_env: str,
    model: str,
    reasoning_effort: str | None,
) -> None:
    calls: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.update(kwargs)
        return object()

    monkeypatch.setenv(model_env, model)
    if getattr(profile, "reasoning_env", None):
        monkeypatch.delenv(profile.reasoning_env, raising=False)
    if reasoning_effort is not None:
        monkeypatch.setenv(profile.reasoning_env, reasoning_effort)
    build_chat_openai(profile, constructor=fake_chat_openai)  # type: ignore[arg-type]

    expected: dict[str, Any] = {
        "model": model,
        "temperature": 0,
        "use_responses_api": True,
    }
    if reasoning_effort is not None:
        expected["reasoning_effort"] = reasoning_effort
    assert calls == expected


def test_conversational_roles_keep_shared_model_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.delenv("OPENAI_MODEL_ORQUESTADOR", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")

    build_chat_openai(
        ORCHESTRATOR_CHAT_PROFILE,
        constructor=lambda **kwargs: calls.update(kwargs) or object(),
    )

    assert calls["model"] == "shared-model"


def test_luna_profile_passes_max_reasoning_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.update(kwargs)
        return object()

    monkeypatch.setenv("OPENAI_MODEL_GENERADOR_CYPHER", "gpt-5.6-luna")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_GENERADOR_CYPHER", "max")

    build_chat_openai(GENERATED_QUERY_CHAT_PROFILE, constructor=fake_chat_openai)

    assert calls["model"] == "gpt-5.6-luna"
    assert calls["reasoning_effort"] == "max"


def test_role_profile_allows_responses_api_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.update(kwargs)
        return object()

    monkeypatch.setenv("OPENAI_MODEL_ANALISTA", "gpt-oss-20b")
    monkeypatch.setenv("OPENAI_USE_RESPONSES_API_ANALISTA", "false")

    build_chat_openai(ANALYST_CHAT_PROFILE, constructor=fake_chat_openai)

    assert calls["use_responses_api"] is False


def test_factory_uses_its_runtime_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_chat_openai(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(llm, "ChatOpenAI", fake_chat_openai)
    monkeypatch.setenv("OPENAI_MODEL_ANALISTA", "gpt-oss-20b")

    build_chat_openai(ANALYST_CHAT_PROFILE)

    assert calls[0]["model"] == "gpt-oss-20b"
