"""Bounded, thread-safe cache for validated read query results."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from agente.utils.cypher_guard import GuardedCypher, guard_cypher
from agente.utils.logger import log_event

DEFAULT_QUERY_CACHE_TTL_SECONDS = 600.0
DEFAULT_QUERY_CACHE_MAX_ENTRIES = 256


def _configured_float(name: str, default: float) -> float:
    """Read one non-negative floating-point cache setting from the environment."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def _configured_size(name: str, default: int) -> int:
    """Read one non-negative integer cache setting from the environment."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


def _validated_key(query: GuardedCypher) -> str | None:
    """Return a digest only when the supplied query still passes the read guard."""
    try:
        validated = guard_cypher(query.text, query.parameters)
        canonical = json.dumps(
            {
                "query": validated.text.strip(),
                "parameters": validated.parameters,
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    """Immutable stored value with its monotonic expiration deadline."""

    expires_at: float
    rows: tuple[dict[str, Any], ...]


class QueryResultCache:
    """Small process-local LRU cache that stores only successful normalized rows."""

    def __init__(
        self,
        *,
        ttl_seconds: float | None = None,
        max_entries: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a cache with explicit bounds and an injectable clock for tests."""
        self._ttl_seconds = (
            _configured_float("QUERY_RESULT_CACHE_TTL_SECONDS", DEFAULT_QUERY_CACHE_TTL_SECONDS)
            if ttl_seconds is None
            else ttl_seconds
        )
        self._max_entries = (
            _configured_size("QUERY_RESULT_CACHE_MAX_ENTRIES", DEFAULT_QUERY_CACHE_MAX_ENTRIES)
            if max_entries is None
            else max_entries
        )
        if self._ttl_seconds < 0:
            raise ValueError("ttl_seconds cannot be negative")
        if self._max_entries < 0:
            raise ValueError("max_entries cannot be negative")
        self._clock = clock
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = RLock()

    def get(self, query: GuardedCypher) -> list[dict[str, Any]] | None:
        """Return a defensive copy for a fresh valid key, otherwise report a miss."""
        key = _validated_key(query)
        if key is None or self._ttl_seconds <= 0 or self._max_entries == 0:
            log_event("query_cache", "lookup", cache_state="miss")
            return None

        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                log_event("query_cache", "lookup", cache_state="miss")
                return None
            if self._clock() >= entry.expires_at:
                del self._entries[key]
                log_event("query_cache", "lookup", cache_state="expired")
                return None
            self._entries.move_to_end(key)
            log_event("query_cache", "lookup", cache_state="hit")
            return deepcopy(list(entry.rows))

    def put(self, query: GuardedCypher, rows: list[dict[str, Any]]) -> None:
        """Store only a valid query's successful row list, without raw query material."""
        key = _validated_key(query)
        if (
            key is None
            or self._ttl_seconds <= 0
            or self._max_entries == 0
            or not isinstance(rows, list)
            or not all(isinstance(row, dict) for row in rows)
        ):
            return

        try:
            json.dumps(rows, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stored_rows = tuple(deepcopy(rows))
        except (TypeError, ValueError):
            return

        with self._lock:
            self._entries[key] = _CacheEntry(
                expires_at=self._clock() + self._ttl_seconds,
                rows=stored_rows,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        """Remove all entries, primarily for lifecycle boundaries and tests."""
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        """Return the current bounded entry count."""
        with self._lock:
            return len(self._entries)


_process_cache: QueryResultCache | None = None
_process_cache_lock = RLock()


def get_process_query_result_cache() -> QueryResultCache:
    """Return the lazily configured cache shared by real graph executions."""
    global _process_cache
    with _process_cache_lock:
        if _process_cache is None:
            _process_cache = QueryResultCache()
        return _process_cache
