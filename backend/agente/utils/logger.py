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
        "cypher_guard",
        "devuelve_respuesta",
        "guarda_memoria_corta",
    }
)
_SAFE_GUARD_DECISIONS = frozenset({"accepted", "rejected"})
_SAFE_EMISSIONS = frozenset({"text", "state", "end", "error"})
_PRIVATE_STATE_FIELDS = frozenset(
    {
        "cypher",
        "filas",
        "historial",
        "memory_scope",
        "parameters",
        "pregunta",
        "pregunta_contextualizada",
        "schema",
    }
)


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
            private_fields = _PRIVATE_STATE_FIELDS if key != "parameter_names" else frozenset()
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
