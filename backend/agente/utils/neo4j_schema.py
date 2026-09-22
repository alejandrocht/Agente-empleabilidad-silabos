"""Load the versioned static Neo4j schema used by Cypher generation."""

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
from agente.utils.schema_ciar import SCHEMA_VERSION, static_schema

load_dotenv()

_schema_cache_lock = RLock()
_schema_cache_snapshot: Neo4jSchemaSnapshot | None = None
_schema_cache_created_at = 0.0


@dataclass(frozen=True, slots=True)
class Neo4jSchemaSnapshot:
    """Text and structured metadata for the active schema contract."""

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
    """Read the live schema for explicit diagnostics, not conversational runtime."""
    started_at = time.perf_counter()
    log_event("neo4j_schema", "extraction_started")
    graph = create_schema_graph()
    try:
        graph.refresh_schema()
        text = graph.get_schema
        structured = deepcopy(graph.get_structured_schema)
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
    """Return the repository's versioned static schema contract."""
    del ttl_seconds  # Kept for compatibility with existing callers.
    global _schema_cache_created_at, _schema_cache_snapshot

    with _schema_cache_lock:
        if force_refresh or _schema_cache_snapshot is None:
            payload = static_schema()
            _schema_cache_snapshot = Neo4jSchemaSnapshot(
                text=(
                    f"ONTOLOGÍA CIAR ESTÁTICA {SCHEMA_VERSION}\n"
                    f"labels: {', '.join(sorted(payload['node_props']))}\n"
                    f"relationships: {len(payload['relationships'])}"
                ),
                structured=payload,
            )
            _schema_cache_created_at = time.monotonic()
            log_event(
                "neo4j_schema",
                "static_contract_loaded",
                schema_version=SCHEMA_VERSION,
                schema_nodes=len(payload["node_props"]),
                schema_relationships=len(payload["relationships"]),
            )

        if _schema_cache_snapshot is None:  # Defensive narrowing for type checkers.
            raise RuntimeError("Static Neo4j schema could not be initialized")
        return deepcopy(_schema_cache_snapshot)


def invalidate_schema_cache() -> None:
    """Clear the in-process copy so the next access reloads the static contract."""
    global _schema_cache_created_at, _schema_cache_snapshot

    with _schema_cache_lock:
        _schema_cache_snapshot = None
        _schema_cache_created_at = 0.0
        log_event("neo4j_schema", "cache_invalidated")
