"""Opt-in human-readable trace of every agent step for interactive debugging."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_VERBOSE: ContextVar[bool] = ContextVar(
    "ciar_verbose",
    default=os.getenv("CIAR_VERBOSE") == "1",
)
_START: ContextVar[float | None] = ContextVar("ciar_verbose_start", default=None)


def verbose_enabled() -> bool:
    """Return whether the current request should emit verbose steps."""
    return _VERBOSE.get()


@contextmanager
def verbose_scope(enabled: bool | None = None) -> Iterator[None]:
    """Enable or disable verbose tracing for the current request scope."""
    if enabled is None:
        enabled = os.getenv("CIAR_VERBOSE") == "1"
    if not enabled:
        yield
        return

    token_verbose = _VERBOSE.set(True)
    token_start = _START.set(time.perf_counter())
    try:
        yield
    finally:
        _VERBOSE.reset(token_verbose)
        _START.reset(token_start)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _elapsed_ms() -> float | None:
    start = _START.get()
    if start is None:
        return None
    return (time.perf_counter() - start) * 1000


def _serialize(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(value)


def verbose_step(
    step: str,
    description: str,
    payload: str | object | None = None,
    *,
    duration_ms: float | None = None,
) -> None:
    """Print one labelled step to stderr when verbose mode is active."""
    if not _VERBOSE.get():
        return

    prefix = f"[{_timestamp()}] [{step}]"
    suffix_parts: list[str] = []
    elapsed = _elapsed_ms()
    if duration_ms is not None:
        suffix_parts.append(f"duración del paso: {duration_ms:.2f} ms")
    if elapsed is not None:
        suffix_parts.append(f"transcurrido total: {elapsed:.2f} ms")
    suffix = f" ({'; '.join(suffix_parts)})" if suffix_parts else ""

    print(f"{prefix} {description}{suffix}", file=sys.stderr)

    if payload is not None:
        text = payload if isinstance(payload, str) else _serialize(payload)
        for line in text.splitlines():
            print(f"{prefix}   {line}", file=sys.stderr)


def verbose_label(step: str, label: str, value: Any) -> None:
    """Print a single labelled value on one line."""
    if not _VERBOSE.get():
        return
    prefix = f"[{_timestamp()}] [{step}]"
    text = value if isinstance(value, str) else _serialize(value)
    # Keep short single-line values compact.
    if "\n" not in text and len(text) < 120:
        print(f"{prefix} {label}: {text}", file=sys.stderr)
    else:
        print(f"{prefix} {label}:", file=sys.stderr)
        for line in text.splitlines():
            print(f"{prefix}   {line}", file=sys.stderr)
