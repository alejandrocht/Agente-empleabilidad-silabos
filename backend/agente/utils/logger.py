"""Central structured logging for the active CIAR backend."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from threading import RLock
from typing import Literal
from uuid import uuid4

LoggerLevel = Literal["debug", "info", "warning", "error", "critical"]

_LOGGER_NAME = "agente"
_DEFAULT_LOG_LEVEL = "INFO"
_TRACE_ID: ContextVar[str | None] = ContextVar("ciar_trace_id", default=None)
_ATTEMPT: ContextVar[int | None] = ContextVar("ciar_attempt", default=None)
_TRACE_ID_PATTERN = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f-]{36})$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,79}$")
_TRACE_SECRET = re.compile(
    r"(?i)(api[_ -]?key|authorization|password|secret|token)\s*[:=]\s*[^\s,;]+"
)
_TRACE_QUOTED = re.compile(r"(['\"])(?:\\.|(?!\1).){0,400}?\1")
_MAX_TRACE_TEXT = 4000
_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
_NODE_ONLY_EVENTS = frozenset({"node_started", "node_completed", "node_failed"})
_NODE_IO_CONTEXT_KEYS = frozenset({"node_input", "node_output"})
_HUMAN_NODE_EVENTS = frozenset({"node_started", "node_completed", "node_failed"})
_NODE_IO_MAX_FIELDS = 64
_NODE_IO_MAX_ITEMS = 16
_NODE_IO_PREVIEW_CHARS = 240
_HUMAN_MAX_VALUE_CHARS = 360
_HUMAN_IGNORED_FIELDS = frozenset({"trace_id", "memory_scope", "historial"})
_HUMAN_TRACE_LOCK = RLock()
_HUMAN_TRACES: dict[
    str, tuple[int, dict[str, int], dict[str, object], dict[str, dict[str, object]]]
] = {}
_NODE_SCOPE_QUIET_LOGGERS = frozenset(
    {
        "langsmith",
        "langchain",
        "httpx",
        "httpcore",
    }
)
_NODE_SCOPE_QUIET_PREFIXES = ("langsmith.", "langchain.", "httpx.", "httpcore.")
_NODE_HARD_SENSITIVE_KEY = re.compile(
    r"(?:api[_ -]?key|authorization|password|secret|token|cookie|credential)",
    re.IGNORECASE,
)
_SAFE_CONTEXT_KEYS = frozenset(
    {
        "action",
        "attempt",
        "cache_state",
        "configured",
        "count",
        "duration_ms",
        "error_type",
        "length",
        "long_enabled",
        "model_configured",
        "candidate_hash",
        "contract_label",
        "node_count",
        "neo4j_category",
        "neo4j_classification",
        "neo4j_code",
        "parameter",
        "query_fingerprint",
        "query_length",
        "query_limit",
        "reason",
        "result_count",
        "route",
        "rows_count",
        "schema_nodes",
        "schema_relationships",
        "short_enabled",
        "stage",
        "status",
        "template_count",
        "turn_count",
        "validation_diagnostics",
        "trace_id",
        "step",
        "input_keys",
        "output_keys",
        "input_size",
        "output_size",
        "prompt_size",
        "response_size",
        "parameter_count",
        "parameter_names",
        "query_structure",
        "schema_text_length",
        "cache_age_ms",
        "cache_ttl_seconds",
        "guard_decision",
        "read_only",
        "emission",
        "emission_index",
        "payload_size",
        "payload_preview",
        "node_input",
        "node_output",
    }
)
_SAFE_STRING_KEYS = frozenset(
    {
        "action",
        "candidate_hash",
        "cache_state",
        "contract_label",
        "error_type",
        "neo4j_category",
        "neo4j_classification",
        "neo4j_code",
        "parameter",
        "query_fingerprint",
        "reason",
        "route",
        "stage",
        "status",
        "trace_id",
        "step",
        "guard_decision",
        "emission",
    }
)
_SAFE_STRING = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_SAFE_STRING_VALUES: dict[str, frozenset[str]] = {
    "action": frozenset({"responder_directo", "usar_plantilla", "generar_cypher"}),
    "cache_state": frozenset({"hit", "miss", "expired"}),
    "reason": frozenset(
        {
            "previous_failure",
            "missing_user",
            "invalid_input",
            "idempotent",
            "invalid_state",
            "unspecified",
            "prompt_injection",
            "cypher_injection",
            "miss",
            "forced",
            "expired",
            "empty_input",
            "input_too_long",
            "invalid_input",
            "invalid_response",
            "invalid_payload",
            "queue_full",
            "duplicate",
            "retry_exhausted",
            "non_transient_failure",
            "shutdown",
            "missing_writer",
            "queue_rejected",
        }
    ),
    "route": frozenset(
        {
            "obtiene_variables",
            "responder_directo",
            "usar_plantilla",
            "generar_cypher",
            "chat",
            "chat_stream",
            "preguntar",
            "conversacion",
            "cypher",
            "finalizar",
        }
    ),
    "status": frozenset({"success", "failed", "skipped", "structured", "degraded"}),
}
_SAFE_DIAGNOSTIC_VALUES: dict[str, frozenset[str]] = {
    "stage": frozenset(
        {"entity_resolution", "dynamic_generation", "dynamic_explain", "dynamic_execution"}
    ),
    "neo4j_category": frozenset(
        {"syntax", "schema", "auth", "transport", "timeout", "unknown"}
    ),
    "neo4j_classification": frozenset(
        {
            "cypher_error",
            "auth_error",
            "transport_error",
            "timeout_error",
            "explain_error",
            "unknown_error",
        }
    ),
}
_SAFE_ERROR_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)$")
_SAFE_HASH = re.compile(r"^[0-9a-f]{64}$")
_SAFE_VALIDATION_DIAGNOSTIC = re.compile(
            r"^loc=(?:plan|extra_field|accion|"
    r"usar_schema|template_id|parametros|objetivo_cypher) "
    r"type=[A-Za-z0-9_.-]{1,80}$"
)
_SENSITIVE_KEY = re.compile(
    r"(?:prompt|question|pregunta|cypher|query|credential|password|secret|token|"
    r"authorization|user|usuario|raw|content|contenido|uuid|id)",
    re.IGNORECASE,
)
_SAFE_STEPS = frozenset(
    {
        "obtiene_pregunta",
        "prompt_injection",
        "contextualiza_pregunta",
        "contextualized_prompt_injection",
        "orquestador",
        "responder_directo",
        "obtiene_schema",
        "construye_cypher",
        "resuelve_entidades",
        "cypher_guard",
        "devuelve_respuesta",
        "redacta_respuesta",
        "guarda_memoria_corta",
    }
)
_SAFE_GUARD_DECISIONS = frozenset({"accepted", "rejected"})
_SAFE_EMISSIONS = frozenset({"text", "state", "end", "error"})
class _CurrentStdoutHandler(logging.Handler):
    """Write JSON to the current stdout object so CLI and test capture both work."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:
            self.handleError(record)


def _logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not any(isinstance(handler, _CurrentStdoutHandler) for handler in logger.handlers):
        handler = _CurrentStdoutHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


def _configured_level() -> int:
    """Read the existing environment convention without failing application startup."""
    configured = os.getenv("CIAR_LOG_LEVEL") or os.getenv("LOG_LEVEL") or _DEFAULT_LOG_LEVEL
    return _LEVELS.get(configured.strip().upper(), logging.INFO)


def trace_id() -> str | None:
    """Return the current request trace identifier, if one is active."""
    return _TRACE_ID.get()


def debug_trace_enabled() -> bool:
    """Enable bounded diagnostic payload previews only by explicit opt-in."""
    return os.getenv("CIAR_DEBUG_TRACE") == "1"


def node_logs_only_enabled() -> bool:
    """Return whether operational output should be restricted to graph node events."""
    configured = os.getenv("CIAR_LOG_SCOPE", "all").strip().lower()
    return configured in {"node", "nodes", "graph_nodes"}


def configure_node_log_scope() -> None:
    """Silence framework/exporter chatter when the operator asks for node-only logs."""
    if not node_logs_only_enabled():
        return

    for name, candidate in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(candidate, logging.Logger):
            continue
        if name in _NODE_SCOPE_QUIET_LOGGERS or name.startswith(_NODE_SCOPE_QUIET_PREFIXES):
            candidate.setLevel(logging.CRITICAL + 1)
            candidate.propagate = False

    for name in ("uvicorn.access", "uvicorn.error", "watchfiles.main"):
        logging.getLogger(name).setLevel(logging.WARNING)


def node_log_values_enabled() -> bool:
    """Allow bounded state previews only during an explicit local debugging session."""
    configured = os.getenv("CIAR_NODE_LOG_VALUES", "0").strip().lower()
    return configured in {"1", "true", "yes", "on", "si", "sí"}


def _node_value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, Mapping):
        return "dict"
    if isinstance(value, (list, tuple, set)):
        return "list"
    return type(value).__name__


def _node_preview(value: object, field: str, depth: int = 0) -> object:
    """Produce a bounded, local-debug preview without serializing credentials."""
    if _NODE_HARD_SENSITIVE_KEY.search(field):
        return "[REDACTADO]"
    if field.casefold() in {
        "filas",
        "parameters",
        "parametros",
        "pregunta",
        "pregunta_contextualizada",
        "respuesta",
        "rows",
    }:
        return "[REDACTADO]"
    if depth >= 3:
        return "[PROFUNDIDAD_LIMITADA]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        single_line = value.replace("\r", "\\r").replace("\n", "\\n")
        if len(single_line) > _NODE_IO_PREVIEW_CHARS:
            return single_line[:_NODE_IO_PREVIEW_CHARS] + "…"
        return single_line
    if isinstance(value, Mapping):
        return {
            str(key): _node_preview(item, str(key), depth + 1)
            for key, item in list(value.items())[:_NODE_IO_MAX_ITEMS]
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple, set)):
        return [_node_preview(item, field, depth + 1) for item in list(value)[:_NODE_IO_MAX_ITEMS]]
    # Dataclasses and schema snapshots can contain large private payloads. Keep their type only.
    return f"<{type(value).__name__}>"


def _node_state_snapshot(value: object) -> object:
    """Summarize a graph state so node boundaries are inspectable and bounded."""
    if not isinstance(value, Mapping):
        return {"type": _node_value_type(value)}

    include_values = node_log_values_enabled()
    snapshot: dict[str, object] = {}
    for field, field_value in list(value.items())[:_NODE_IO_MAX_FIELDS]:
        if not isinstance(field, str) or not _SAFE_IDENTIFIER.fullmatch(field):
            continue
        metadata: dict[str, object] = {"type": _node_value_type(field_value)}
        if isinstance(field_value, str):
            metadata["chars"] = len(field_value)
        elif isinstance(field_value, Mapping):
            metadata["keys"] = len(field_value)
        elif isinstance(field_value, (list, tuple, set)):
            metadata["items"] = len(field_value)
        if include_values:
            metadata["preview"] = _node_preview(field_value, field)
        snapshot[field] = metadata
    if len(value) > _NODE_IO_MAX_FIELDS:
        snapshot["_truncated"] = {"type": "bool", "preview": True}
    return snapshot


def _configured_log_format() -> str:
    """Return the operator-selected output format for local diagnostics."""
    configured = os.getenv("CIAR_LOG_FORMAT", "json").strip().lower()
    return "human" if configured in {"human", "text", "texto"} else "json"


def _human_value(value: object) -> str:
    """Render one already-sanitized node field without adding log noise."""
    if not isinstance(value, Mapping):
        return _human_clip(str(value))

    if "preview" in value:
        preview = value["preview"]
        if preview is None:
            return "null"
        if isinstance(preview, str) and preview.startswith("<") and preview.endswith(">"):
            return preview
        try:
            rendered = json.dumps(preview, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            rendered = str(preview)
        return _human_clip(rendered)

    value_type = value.get("type", "valor")
    if value_type == "str" and isinstance(value.get("chars"), int):
        return f"<str; {value['chars']} caracteres>"
    if value_type == "dict" and isinstance(value.get("keys"), int):
        return f"<dict; {value['keys']} claves>"
    if value_type == "list" and isinstance(value.get("items"), int):
        return f"<list; {value['items']} elementos>"
    return f"<{value_type}>"


def _human_clip(value: str) -> str:
    if len(value) <= _HUMAN_MAX_VALUE_CHARS:
        return value
    return value[:_HUMAN_MAX_VALUE_CHARS] + "…"


def _human_fields(snapshot: object) -> list[str]:
    """Render a concise list of fields from a sanitized node snapshot."""
    if not isinstance(snapshot, Mapping):
        return [f"    valor: {_human_value(snapshot)}"]

    lines: list[str] = []
    for field, value in snapshot.items():
        if not isinstance(field, str) or field in _HUMAN_IGNORED_FIELDS or field == "_truncated":
            continue
        lines.append(f"    {field}: {_human_value(value)}")
    return lines or ["    (sin datos nuevos)"]


def _human_node_event(event: str, context: Mapping[str, object]) -> str | None:
    """Build one readable node block from the sanitized event context.

    ``node_started`` is buffered so each node is printed once with both its
    input and output. The input is reduced to fields that changed since the
    previous node, which avoids repeating the accumulated LangGraph state.
    """
    trace = context.get("trace_id")
    trace_key = trace if isinstance(trace, str) else "sin-trace"
    trace_text = trace_key[:8]
    step = context.get("step")
    step_text = step if isinstance(step, str) else "desconocido"

    with _HUMAN_TRACE_LOCK:
        tracker = _HUMAN_TRACES.get(trace_key)
        if event == "node_started":
            snapshot = context.get("node_input")
            previous_snapshot: Mapping[str, object] = tracker[2] if tracker else {}
            next_number = tracker[0] if tracker else 1
            indexes = dict(tracker[1]) if tracker else {}
            pending = dict(tracker[3]) if tracker else {}
            current_snapshot = snapshot if isinstance(snapshot, Mapping) else {}
            changed: dict[str, object] = {}
            # Keep the user question visible at every boundary. Other
            # unchanged fields are omitted because the graph carries them.
            if "pregunta" in current_snapshot:
                changed["pregunta"] = current_snapshot["pregunta"]
            changed.update(
                {
                    key: value
                    for key, value in current_snapshot.items()
                    if key != "pregunta"
                    and (key not in previous_snapshot or previous_snapshot[key] != value)
                }
            )
            indexes[step_text] = next_number
            pending[step_text] = changed
            _HUMAN_TRACES[trace_key] = (
                next_number + 1,
                indexes,
                dict(current_snapshot),
                pending,
            )
            return None

        if tracker is None:
            number = 1
            pending = {}
            input_snapshot: object = context.get("node_input", {})
        else:
            number = tracker[1].get(step_text, max(tracker[0] - 1, 1))
            pending = dict(tracker[3])
            input_snapshot = pending.pop(step_text, {})
            _HUMAN_TRACES[trace_key] = (tracker[0], dict(tracker[1]), tracker[2], pending)

    lines: list[str] = []
    is_first_node = number == 1
    if tracker is None:
        question_snapshot = (
            input_snapshot.get("pregunta")
            if isinstance(input_snapshot, Mapping)
            else None
        )
        lines.extend(
            [
                f"----- START trace={trace_text} -----",
                f"Pregunta: {_human_value(question_snapshot)}",
            ]
        )
    elif is_first_node:
        question_snapshot = (
            input_snapshot.get("pregunta")
            if isinstance(input_snapshot, Mapping)
            else None
        )
        lines.extend(
            [
                f"----- START trace={trace_text} -----",
                f"Pregunta: {_human_value(question_snapshot)}",
            ]
        )

    lines.extend(
        [
            "",
            f"[{number:02d}] Nodo: {step_text}",
            "  Enviados:",
            *_human_fields(input_snapshot),
        ]
    )
    if event == "node_failed":
        lines.extend(
            [
                "  Recibidos:",
                f"    estado: ERROR ({context.get('error_type', 'Error')})",
            ]
        )
        lines.append(f"\n----- END estado=failed trace={trace_text} -----")
        with _HUMAN_TRACE_LOCK:
            _HUMAN_TRACES.pop(trace_key, None)
        return "\n".join(lines)

    lines.extend(["  Recibidos:", *_human_fields(context.get("node_output", {}))])
    status = context.get("status")
    if isinstance(status, str):
        lines.append(f"  Estado: {status}")
    if step_text == "guarda_memoria_corta":
        lines.append(f"\n----- END estado={status or 'success'} trace={trace_text} -----")
        with _HUMAN_TRACE_LOCK:
            _HUMAN_TRACES.pop(trace_key, None)
    return "\n".join(lines)


@contextmanager
def trace_context(value: str | None = None) -> Iterator[str]:
    """Correlate nested API, graph, LLM, and database events safely."""
    candidate = value or uuid4().hex
    if not _TRACE_ID_PATTERN.fullmatch(candidate):
        candidate = uuid4().hex
    token = _TRACE_ID.set(candidate)
    try:
        yield candidate
    finally:
        _TRACE_ID.reset(token)


@contextmanager
def attempt_context(attempt: int) -> Iterator[None]:
    """Attach the active bounded retry attempt to nested operational events."""
    token = _ATTEMPT.set(attempt if isinstance(attempt, int) and attempt > 0 else 1)
    try:
        yield
    finally:
        _ATTEMPT.reset(token)


def _redact_trace_text(value: str, *, max_length: int = _MAX_TRACE_TEXT) -> str:
    """Bound diagnostic text and remove common secret assignments and literals."""
    redacted = _TRACE_SECRET.sub(r"\1=<REDACTED>", value)
    redacted = _TRACE_QUOTED.sub("<REDACTED>", redacted)
    if len(redacted) > max_length:
        return redacted[:max_length] + "<TRUNCATED>"
    return redacted


def _safe_value(key: str, value: object) -> object:
    if key in _NODE_IO_CONTEXT_KEYS:
        return _node_state_snapshot(value)
    if key in {"payload_preview", "query_structure"}:
        return None
    safe_diagnostic_key = key in {
        "candidate_hash",
        "contract_label",
        "neo4j_category",
        "neo4j_classification",
        "neo4j_code",
        "parameter",
        "query_fingerprint",
        "query_length",
        "query_limit",
        "query_structure",
        "stage",
        "validation_diagnostics",
        "payload_preview",
        "trace_id",
        "step",
        "input_keys",
        "output_keys",
        "input_size",
        "output_size",
        "prompt_size",
        "response_size",
        "parameter_count",
        "parameter_names",
        "query_structure",
        "schema_text_length",
        "cache_age_ms",
        "cache_ttl_seconds",
        "guard_decision",
        "read_only",
        "emission",
        "emission_index",
        "payload_size",
        "payload_preview",
    }
    if key not in _SAFE_CONTEXT_KEYS or (_SENSITIVE_KEY.search(key) and not safe_diagnostic_key):
        return None
    if key == "validation_diagnostics":
        if not isinstance(value, (list, tuple)):
            return None
        return [
            item
            for item in value[:8]
            if isinstance(item, str) and _SAFE_VALIDATION_DIAGNOSTIC.fullmatch(item)
        ]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else None
    if isinstance(value, str):
        if key == "trace_id":
            return value if _TRACE_ID_PATTERN.fullmatch(value) else None
        if key == "step":
            return value if value in _SAFE_STEPS else None
        if key in {"input_keys", "output_keys", "parameter_names"}:
            return None
        if key == "guard_decision":
            return value if value in _SAFE_GUARD_DECISIONS else None
        if key == "emission":
            return value if value in _SAFE_EMISSIONS else None
        if key not in _SAFE_STRING_KEYS:
            return None
        if key in {"candidate_hash", "query_fingerprint"}:
            return value if _SAFE_HASH.fullmatch(value) else None
        if key in _SAFE_DIAGNOSTIC_VALUES:
            return value if value in _SAFE_DIAGNOSTIC_VALUES[key] else None
        if key in {"contract_label", "neo4j_code", "parameter"}:
            return value if _SAFE_STRING.fullmatch(value) else None
        if key == "error_type":
            return value if _SAFE_ERROR_TYPE.fullmatch(value) else None
        if value not in _SAFE_STRING_VALUES.get(key, frozenset()):
            return None
        if not _SAFE_STRING.fullmatch(value):
            return None
        return value
    if isinstance(value, (list, tuple)):
        if key in {"input_keys", "output_keys", "parameter_names"}:
            # Field names are safe metadata. Keep the graph's private state
            # names visible so the boundary summary matches the snapshots;
            # values remain gated by CIAR_NODE_LOG_VALUES and redaction.
            private_fields = frozenset()
            return [
                item
                for item in value[:32]
                if isinstance(item, str)
                and item not in private_fields
                and _SAFE_IDENTIFIER.fullmatch(item)
            ]
        safe_items = [_safe_value(key, item) for item in value]
        return [item for item in safe_items if item is not None]
    if isinstance(value, Mapping):
        safe_mapping: dict[str, object] = {}
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                continue
            safe_nested = _safe_value(nested_key, nested_value)
            if safe_nested is not None:
                safe_mapping[nested_key] = safe_nested
        return safe_mapping
    return None


def sanitize_context(context: Mapping[str, object] | None) -> dict[str, object]:
    """Keep only bounded operational metadata and drop request-owned data."""
    if not context:
        return {}
    sanitized: dict[str, object] = {}
    for key, value in context.items():
        if not isinstance(key, str):
            continue
        safe_value = _safe_value(key, value)
        if safe_value is not None:
            sanitized[key] = safe_value
    return sanitized


def log_event(
    component: str,
    event: str,
    *,
    level: LoggerLevel = "info",
    context: Mapping[str, object] | None = None,
    **extra_context: object,
) -> None:
    """Emit one stable JSON event with only safe operational context."""
    if not _SAFE_STRING.fullmatch(component) or not _SAFE_STRING.fullmatch(event):
        raise ValueError("component and event must be stable ASCII names")

    logger = _logger()
    logger.setLevel(_configured_level())
    numeric_level = _LEVELS[level.upper()]
    if not logger.isEnabledFor(numeric_level):
        return

    merged_context = dict(context or {})
    merged_context.update(extra_context)
    configure_node_log_scope()
    if node_logs_only_enabled() and (component, event) not in {
        ("graph", node_event) for node_event in _NODE_ONLY_EVENTS
    }:
        return
    active_trace_id = trace_id()
    if active_trace_id is not None and "trace_id" not in merged_context:
        merged_context["trace_id"] = active_trace_id
    active_attempt = _ATTEMPT.get()
    if active_attempt is not None and "attempt" not in merged_context:
        merged_context["attempt"] = active_attempt
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": level,
        "logger": _LOGGER_NAME,
        "component": component,
        "event": event,
        "context": sanitize_context(merged_context),
    }
    safe_context = entry["context"]
    if (
        _configured_log_format() == "human"
        and component == "graph"
        and event in _HUMAN_NODE_EVENTS
        and isinstance(safe_context, Mapping)
    ):
        human_event = _human_node_event(event, safe_context)
        if human_event is None:
            return
        logger.log(numeric_level, human_event)
        return

    logger.log(numeric_level, json.dumps(entry, ensure_ascii=False, allow_nan=False))


def log_error(
    component: str,
    event: str,
    error: BaseException,
    *,
    context: Mapping[str, object] | None = None,
    **extra_context: object,
) -> None:
    """Log an exception type without serializing its message or request data."""
    safe_context = dict(context or {})
    safe_context.update(extra_context)
    safe_context["error_type"] = type(error).__name__
    log_event(component, event, level="error", context=safe_context)
