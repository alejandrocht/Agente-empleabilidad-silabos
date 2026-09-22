"""Regression coverage for opt-in LangSmith tracing."""

from __future__ import annotations

import pytest

from agente.observabilidad import langsmith as observabilidad


def _ejecutar() -> int:
    return 7


def test_enabled_tracing_without_api_key_is_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    assert observabilidad.tracing_activo() is False
    assert (
        observabilidad.ejecutar_flujo(
            _ejecutar,
            run_name="test.run",
            inputs={},
            tags=[],
            metadata={},
        )
        == 7
    )


def test_disabled_tracing_remains_a_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    cliente = object()

    assert observabilidad.tracing_activo() is False
    assert observabilidad.envolver_cliente_openai(cliente) is cliente
    assert observabilidad.configuracion_llm("analista_curricular") is None
    assert (
        observabilidad.ejecutar_flujo(
            _ejecutar,
            run_name="test.run",
            inputs={},
            tags=[],
            metadata={},
        )
        == 7
    )
