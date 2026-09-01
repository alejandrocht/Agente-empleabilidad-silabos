"""Central ChatOpenAI profiles for the active CIAR backend."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

ChatOpenAIConstructor = Callable[..., Any]


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a stable default."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ChatOpenAIProfile:
    """Configuration for one role without changing its environment contract."""

    model_env: str
    reasoning_env: str | None = None
    default_model: str | None = None
    default_reasoning_effort: str | None = None
    global_model_fallback: bool = True
    strip_model_env: bool = False
    use_responses_api: bool | None = None
    use_responses_api_env: str | None = None
    include_api_key: bool = False
    include_base_url: bool = False
    include_reasoning_effort: bool = False
    timeout: float | None = None
    max_retries: int | None = None


# Each conversational responsibility has one explicit model. Direct and
# grounded answers intentionally share the analyst profile.
ORCHESTRATOR_CHAT_PROFILE = ChatOpenAIProfile(
    model_env="OPENAI_MODEL_ORQUESTADOR",
    reasoning_env="OPENAI_REASONING_EFFORT_ORQUESTADOR",
    default_reasoning_effort=None,
    global_model_fallback=True,
    use_responses_api=True,
    use_responses_api_env="OPENAI_USE_RESPONSES_API_ORQUESTADOR",
)
GENERATED_QUERY_CHAT_PROFILE = ChatOpenAIProfile(
    model_env="OPENAI_MODEL_GENERADOR_CYPHER",
    reasoning_env="OPENAI_REASONING_EFFORT_GENERADOR_CYPHER",
    default_reasoning_effort=None,
    global_model_fallback=True,
    use_responses_api=True,
    use_responses_api_env="OPENAI_USE_RESPONSES_API_GENERADOR_CYPHER",
)
ANALYST_CHAT_PROFILE = ChatOpenAIProfile(
    model_env="OPENAI_MODEL_ANALISTA",
    reasoning_env="OPENAI_REASONING_EFFORT_ANALISTA",
    default_reasoning_effort=None,
    global_model_fallback=True,
    use_responses_api=True,
    use_responses_api_env="OPENAI_USE_RESPONSES_API_ANALISTA",
)


def _model_for_profile(profile: ChatOpenAIProfile) -> str:
    configured = os.getenv(profile.model_env)
    if profile.strip_model_env and configured is not None:
        configured = configured.strip()
    if configured:
        return configured
    if profile.global_model_fallback:
        shared = os.getenv("OPENAI_MODEL")
        if shared:
            return shared
    if profile.default_model:
        return profile.default_model
    if profile.global_model_fallback:
        raise RuntimeError(f"{profile.model_env} u OPENAI_MODEL debe estar configurado")
    raise RuntimeError(f"{profile.model_env} debe estar configurado")


def _reasoning_for_profile(profile: ChatOpenAIProfile) -> str | None:
    """Return a configured reasoning effort, or None when the role has no default."""
    if profile.reasoning_env is not None:
        value = os.getenv(profile.reasoning_env)
        if value is not None and value.strip():
            return value.strip()
        return profile.default_reasoning_effort
    return profile.default_reasoning_effort


def build_chat_openai(
    profile: ChatOpenAIProfile,
    *,
    constructor: ChatOpenAIConstructor | None = None,
    timeout: float | None = None,
) -> ChatOpenAI:
    """Build a role-specific model while keeping provider settings centralized."""
    kwargs: dict[str, Any] = {
        "model": _model_for_profile(profile),
        "temperature": 0,
    }
    if profile.use_responses_api_env is not None:
        kwargs["use_responses_api"] = _env_bool(
            profile.use_responses_api_env, profile.use_responses_api or False
        )
    elif profile.use_responses_api is not None:
        kwargs["use_responses_api"] = profile.use_responses_api
    reasoning_effort = _reasoning_for_profile(profile)
    if reasoning_effort is not None:
        kwargs["reasoning_effort"] = reasoning_effort
    if profile.include_api_key:
        api_key = os.getenv("OPENAI_API_KEY")
        kwargs["api_key"] = SecretStr(api_key) if api_key else None
    if profile.include_base_url:
        kwargs["base_url"] = os.getenv("OPENAI_BASE_URL") or None
    configured_timeout = timeout if timeout is not None else profile.timeout
    if configured_timeout is not None:
        kwargs["timeout"] = configured_timeout
    if profile.max_retries is not None:
        kwargs["max_retries"] = profile.max_retries
    return (constructor or ChatOpenAI)(**kwargs)
