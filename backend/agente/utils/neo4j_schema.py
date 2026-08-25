"""Read and cache the structured Neo4j schema used by dynamic Cypher."""

from __future__ import annotations

import os
import time
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from dotenv import load_dotenv
from langchain_neo4j import Neo4jGraph

from agente.utils.logger import log_event

load_dotenv()

DEFAULT_SCHEMA_CACHE_TTL_SECONDS = 900.0
REQUIRED_CIAR_LABELS = frozenset({"Carrera", "Empresa", "OfertaLaboral"})
_schema_cache_lock = RLock()
_schema_cache_snapshot: Neo4jSchemaSnapshot | None = None
_schema_cache_created_at = 0.0


@dataclass(frozen=True, slots=True)
class Neo4jSchemaSnapshot:
    """Text and structured metadata for one Neo4j schema snapshot."""

    text: str
    structured: dict[str, Any]


class Neo4jSchemaMismatchError(ValueError):
    """The database was reachable but does not expose the CIAR graph contract."""

    def __init__(self, missing_labels: list[str]) -> None:
        self.missing_labels = tuple(sorted(missing_labels))
        super().__init__(
            "Neo4j schema is not the CIAR graph; missing labels: "
            + ", ".join(self.missing_labels)
        )


def _configured_cache_ttl() -> float:
    """Return the configured cache TTL, defaulting to fifteen minutes."""
    raw_value = os.getenv("NEO4J_SCHEMA_CACHE_TTL_SECONDS")
    if raw_value is None:
        return DEFAULT_SCHEMA_CACHE_TTL_SECONDS
    try:
        ttl = float(raw_value)
    except ValueError as exc:
        raise ValueError("NEO4J_SCHEMA_CACHE_TTL_SECONDS must be numeric") from exc
    if ttl < 0:
        raise ValueError("NEO4J_SCHEMA_CACHE_TTL_SECONDS cannot be negative")
    return ttl


def create_schema_graph() -> Neo4jGraph:
    """Create a Neo4jGraph configured from the project's existing variables."""
    return Neo4jGraph(
        url=os.environ["NEO4J_URI"],
        username=os.environ["NEO4J_USER"],
        password=os.environ["NEO4J_PASSWORD"],
        database=os.getenv("NEO4J_DATABASE") or None,
        refresh_schema=False,
        enhanced_schema=False,
    )


def extract_neo4j_schema() -> Neo4jSchemaSnapshot:
    """Read the live schema and return only representations consumed downstream."""
    started_at = time.perf_counter()
    log_event("neo4j_schema", "extraction_started")
    graph = create_schema_graph()
    try:
        graph.refresh_schema()
        text = graph.get_schema
        structured = deepcopy(graph.get_structured_schema)
        available_labels = set(structured.get("node_props", {}))
        missing_labels = sorted(REQUIRED_CIAR_LABELS - available_labels)
        if missing_labels:
            raise Neo4jSchemaMismatchError(missing_labels)
        snapshot = Neo4jSchemaSnapshot(
            text=text,
            structured=structured,
        )
        log_event(
            "neo4j_schema",
            "extraction_completed",
            status="success",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            schema_nodes=len(structured.get("node_props", {})),
            schema_relationships=len(structured.get("relationships", [])),
            schema_text_length=len(text),
        )
        return snapshot
    finally:
        graph.close()


def get_cached_neo4j_schema(
    *,
    force_refresh: bool = False,
    ttl_seconds: float | None = None,
) -> Neo4jSchemaSnapshot:
    """Return a cached schema snapshot and refresh it only when required."""
    global _schema_cache_created_at, _schema_cache_snapshot

    ttl = _configured_cache_ttl() if ttl_seconds is None else ttl_seconds
    if ttl < 0:
        raise ValueError("ttl_seconds cannot be negative")

    with _schema_cache_lock:
        now = time.monotonic()
        cache_age_ms = (
            round(max(0.0, (now - _schema_cache_created_at) * 1000), 2)
            if _schema_cache_snapshot is not None
            else 0.0
        )
        cache_is_fresh = (
            _schema_cache_snapshot is not None
            and now - _schema_cache_created_at < ttl
        )
        if force_refresh or not cache_is_fresh:
            log_event(
                "neo4j_schema",
                "cache_refresh",
                reason=(
                    "miss"
                    if _schema_cache_snapshot is None
                    else "forced"
                    if force_refresh
                    else "expired"
                ),
                cache_state="miss" if _schema_cache_snapshot is None else "expired",
                cache_age_ms=cache_age_ms,
                cache_ttl_seconds=ttl,
            )
            _schema_cache_snapshot = extract_neo4j_schema()
            _schema_cache_created_at = now
        else:
            log_event(
                "neo4j_schema",
                "cache_lookup",
                cache_state="hit",
                cache_age_ms=cache_age_ms,
                cache_ttl_seconds=ttl,
            )

        if _schema_cache_snapshot is None:  # Defensive narrowing for type checkers.
            raise RuntimeError("Neo4j schema cache could not be initialized")
        return deepcopy(_schema_cache_snapshot)


def invalidate_schema_cache() -> None:
    """Clear the snapshot so the next access reloads the live Neo4j schema."""
    global _schema_cache_created_at, _schema_cache_snapshot

    with _schema_cache_lock:
        _schema_cache_snapshot = None
        _schema_cache_created_at = 0.0
        log_event("neo4j_schema", "cache_invalidated")
