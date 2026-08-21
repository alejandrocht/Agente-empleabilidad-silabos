from __future__ import annotations

import json

from agente.utils.logger import log_error, log_event, trace_context


def read_log(capsys) -> dict[str, object]:
    """Decode the single structured event emitted by the logger."""
    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    assert len(lines) == 1
    return json.loads(lines[0])


def test_log_event_emits_stable_json_shape(capsys) -> None:
    log_event("test_component", "operation_completed", count=3, status="success")

    entry = read_log(capsys)

    assert set(entry) == {"timestamp", "level", "logger", "component", "event", "context"}
    assert entry["level"] == "info"
    assert entry["logger"] == "agente"
    assert entry["component"] == "test_component"
    assert entry["event"] == "operation_completed"
    assert entry["context"] == {"count": 3, "status": "success"}


def test_log_event_drops_prompts_queries_secrets_ids_and_raw_values(capsys) -> None:
    sentinel = "MUST_NOT_BE_LOGGED"

    log_event(
        "test_component",
        "operation_completed",
        context={
            "count": 2,
            "prompt": sentinel,
            "cypher": sentinel,
            "password": sentinel,
            "user_id": sentinel,
            "question": sentinel,
            "reason": "Alice",
        },
    )

    entry = read_log(capsys)

    assert entry["context"] == {"count": 2}
    assert sentinel not in json.dumps(entry)


def test_log_error_keeps_only_exception_type(capsys) -> None:
    error = RuntimeError("private prompt and secret token")

    log_error("test_component", "operation_failed", error)

    entry = read_log(capsys)

    assert entry["level"] == "error"
    assert entry["context"] == {"error_type": "RuntimeError"}
    assert "private prompt" not in json.dumps(entry)


def test_log_level_is_configurable(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CIAR_LOG_LEVEL", "ERROR")

    log_event("test_component", "ignored_info")
    log_event("test_component", "visible_error", level="error")

    entry = read_log(capsys)
    assert entry["event"] == "visible_error"


def test_trace_context_correlates_bounded_query_shape_and_attempt(capsys) -> None:
    with trace_context("0123456789abcdef0123456789abcdef"):
        log_event(
            "dynamic_query",
            "guard_accepted",
            attempt=2,
            step="construye_cypher",
            status="success",
            query_structure=(
                "MATCH (n:Empresa) WHERE n.nombre = 'PRIVATE_COMPANY' "
                "RETURN n.nombre LIMIT $limite"
            ),
            parameter_names=["limite"],
            payload_preview="password=PRIVATE_PASSWORD",
        )

    entry = read_log(capsys)
    serialized = json.dumps(entry)

    assert entry["context"]["trace_id"] == "0123456789abcdef0123456789abcdef"
    assert entry["context"]["attempt"] == 2
    assert entry["context"]["step"] == "construye_cypher"
    assert entry["context"]["parameter_names"] == ["limite"]
    assert "PRIVATE_COMPANY" not in serialized
    assert "PRIVATE_PASSWORD" not in serialized
    assert "query_structure" not in entry["context"]
    assert "payload_preview" not in entry["context"]
