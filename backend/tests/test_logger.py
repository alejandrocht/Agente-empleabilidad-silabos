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


def test_node_logs_expose_state_shape_without_values_by_default(capsys, monkeypatch) -> None:
    monkeypatch.delenv("CIAR_NODE_LOG_VALUES", raising=False)
    question = "¿De qué cursos es coordinadora Angela Mayhua?"

    log_event(
        "graph",
        "node_completed",
        step="construye_cypher",
        node_input={
            "pregunta": question,
            "parameters": {"coordinador": "Angela Mayhua"},
        },
        node_output={
            "cypher": "MATCH (c:Curso) RETURN c",
            "parameters": {"coordinador": "Angela Mayhua", "limite": 20},
        },
    )

    entry = read_log(capsys)
    serialized = json.dumps(entry, ensure_ascii=False)

    assert entry["context"]["node_input"]["pregunta"] == {
        "type": "str",
        "chars": len(question),
    }
    assert entry["context"]["node_output"]["parameters"] == {"type": "dict", "keys": 2}
    assert "Angela Mayhua" not in serialized
    assert "MATCH (c:Curso)" not in serialized


def test_node_completion_keeps_only_the_output_snapshot(capsys) -> None:
    log_event(
        "graph",
        "node_completed",
        step="resuelve_entidades",
        status="success",
        node_output={"entity_resolution": "unique"},
    )

    entry = read_log(capsys)
    assert "node_input" not in entry["context"]
    assert entry["context"]["node_output"]["entity_resolution"] == {
        "type": "str",
        "chars": 6,
    }


def test_node_logs_can_include_bounded_values_when_explicitly_enabled(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CIAR_NODE_LOG_VALUES", "1")

    log_event(
        "graph",
        "node_completed",
        step="obtiene_pregunta",
        node_input={"pregunta": "Angela Mayhua"},
        node_output={"error": None},
    )

    entry = read_log(capsys)
    assert entry["context"]["node_input"]["pregunta"]["preview"] == "[REDACTADO]"


def test_node_value_preview_redacts_credentials(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CIAR_NODE_LOG_VALUES", "1")

    log_event(
        "graph",
        "node_completed",
        step="obtiene_pregunta",
        node_input={"api_key": "PRIVATE_API_KEY", "password": "PRIVATE_PASSWORD"},
    )

    entry = read_log(capsys)
    serialized = json.dumps(entry)
    assert "PRIVATE_API_KEY" not in serialized
    assert "PRIVATE_PASSWORD" not in serialized
    assert entry["context"]["node_input"]["api_key"]["preview"] == "[REDACTADO]"


def test_node_log_scope_filters_non_node_events(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CIAR_LOG_SCOPE", "nodes")

    log_event("api", "request_started", route="chat_stream")
    log_event("graph", "node_started", step="obtiene_pregunta", node_input={})

    entry = read_log(capsys)
    assert entry["component"] == "graph"
    assert entry["event"] == "node_started"


def test_node_logs_keep_all_active_node_names(capsys) -> None:
    for step in ("resuelve_entidades", "redacta_respuesta"):
        log_event("graph", "node_completed", step=step, status="success")

    entries = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line
    ]

    assert [entry["context"]["step"] for entry in entries] == [
        "resuelve_entidades",
        "redacta_respuesta",
    ]


def test_human_node_logs_group_input_and_output_in_one_block(capsys, monkeypatch) -> None:
    monkeypatch.setenv("CIAR_LOG_SCOPE", "nodes")
    monkeypatch.setenv("CIAR_LOG_FORMAT", "human")
    monkeypatch.setenv("CIAR_NODE_LOG_VALUES", "1")

    with trace_context("0123456789abcdef0123456789abcdef"):
        log_event(
            "graph",
            "node_started",
            step="obtiene_pregunta",
            node_input={"pregunta": "¿Qué cursos hay?"},
        )
        log_event(
            "graph",
            "node_completed",
            step="obtiene_pregunta",
            status="success",
            node_output={"pregunta": "¿Qué cursos hay?"},
        )
        log_event(
            "graph",
            "node_started",
            step="guarda_memoria_corta",
            node_input={"pregunta": "¿Qué cursos hay?", "respuesta": "Hay 2."},
        )
        log_event(
            "graph",
            "node_completed",
            step="guarda_memoria_corta",
            status="success",
            node_output={},
        )

    output = capsys.readouterr().out
    assert "----- START trace=01234567 -----" in output
    assert "[01] Nodo: obtiene_pregunta" in output
    assert 'pregunta: "[REDACTADO]"' in output
    assert "[02] Nodo: guarda_memoria_corta" in output
    assert 'respuesta: "[REDACTADO]"' in output
    assert "----- END estado=success trace=01234567 -----" in output
    assert '"node_started"' not in output
