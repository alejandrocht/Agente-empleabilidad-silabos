"""Async, fail-closed Neo4j query gateway for domain reads."""

from __future__ import annotations

import hashlib
import math
import os
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal, cast

from dotenv import load_dotenv
from neo4j import AsyncGraphDatabase, Query, RoutingControl
from neo4j.exceptions import (
    AuthError,
    ClientError,
    CypherSyntaxError,
    CypherTypeError,
    ServiceUnavailable,
    SessionExpired,
)
from neo4j.graph import Node, Path, Relationship
from neo4j.spatial import Point
from neo4j.time import Date, DateTime, Duration, Time

from agente.utils.cypher_guard import GuardedCypher, guard_cypher
from agente.utils.logger import log_error, log_event

load_dotenv()

DEFAULT_QUERY_TIMEOUT_SECONDS = 10.0
DEFAULT_NEO4J_DATABASE = "neo4j"


class Neo4jQueryError(RuntimeError):
    """Raised when Neo4j cannot prove or execute a safe domain read."""


ExplainFailureCategory = Literal["syntax", "schema"]
DiagnosticStage = Literal[
    "entity_resolution",
    "dynamic_generation",
    "dynamic_explain",
    "dynamic_execution",
]
Neo4jErrorCategory = Literal["syntax", "schema", "auth", "transport", "timeout", "unknown"]
Neo4jErrorClassification = Literal[
    "cypher_error",
    "auth_error",
    "transport_error",
    "timeout_error",
    "explain_error",
    "unknown_error",
]
_DIAGNOSTIC_STAGES = frozenset(
    {"entity_resolution", "dynamic_generation", "dynamic_explain", "dynamic_execution"}
)


@dataclass(frozen=True, slots=True)
class Neo4jErrorDiagnostic:
    """Stable Neo4j error metadata safe for structured operational logs."""

    code: str | None
    category: Neo4jErrorCategory
    classification: Neo4jErrorClassification


class Neo4jExplainError(Neo4jQueryError):
    """A bounded, classified EXPLAIN failure safe for one generator correction retry."""

    def __init__(
        self,
        category: ExplainFailureCategory,
        *,
        code: str | None = None,
        cause: BaseException | None = None,
    ):
        self.category = category
        self.code = code or (_stable_neo4j_code(cause) if cause is not None else None)
        self.classification: Neo4jErrorClassification = (
            _classify_neo4j_exception(cause)[1]
            if cause is not None
            else "explain_error"
        )
        message = (
            "Neo4j reported a schema warning during EXPLAIN"
            if category == "schema"
            else "Neo4j EXPLAIN rejected the read query"
        )
        super().__init__(message)


_SAFE_NEO4J_CODE = re.compile(r"^Neo\.[A-Za-z0-9_.-]{1,159}$")


def _stable_neo4j_code(error: BaseException | None) -> str | None:
    if error is None:
        return None
    code = getattr(error, "code", None)
    if code == "Neo.DatabaseError.General.UnknownError":
        if isinstance(error, CypherSyntaxError):
            return "Neo.ClientError.Statement.SyntaxError"
        if isinstance(error, CypherTypeError):
            return "Neo.ClientError.Statement.SemanticError"
    return code if isinstance(code, str) and _SAFE_NEO4J_CODE.fullmatch(code) else None


def _classify_neo4j_exception(
    error: BaseException,
) -> tuple[Neo4jErrorCategory, Neo4jErrorClassification]:
    if isinstance(error, Neo4jExplainError):
        return error.category, error.classification
    if isinstance(error, AuthError):
        return "auth", "auth_error"
    if isinstance(error, (ServiceUnavailable, SessionExpired, ConnectionError)):
        return "transport", "transport_error"
    if isinstance(error, TimeoutError):
        return "timeout", "timeout_error"
    if isinstance(error, CypherSyntaxError):
        return "syntax", "cypher_error"
    if isinstance(error, CypherTypeError):
        return "schema", "cypher_error"
    code = _stable_neo4j_code(error) or ""
    if code.startswith("Neo.ClientError.Security."):
        return "auth", "auth_error"
    if code.startswith("Neo.TransientError."):
        return "transport", "transport_error"
    if code == "Neo.ClientError.Statement.SyntaxError":
        return "syntax", "cypher_error"
    if code in {
        "Neo.ClientError.Statement.SemanticError",
        "Neo.ClientError.Statement.EntityNotFound",
    }:
        return "schema", "cypher_error"
    return "unknown", "unknown_error"


def classify_neo4j_error(error: BaseException) -> Neo4jErrorDiagnostic:
    """Extract only stable Neo4j code, category, and exception classification."""
    category, classification = _classify_neo4j_exception(error)
    return Neo4jErrorDiagnostic(
        code=_stable_neo4j_code(error),
        category=category,
        classification=classification,
    )


def query_fingerprint(query: str) -> str:
    """Return a deterministic digest without retaining or logging the query text."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def neo4j_diagnostic_context(
    *,
    stage: DiagnosticStage,
    duration_ms: float,
    cypher: str | None = None,
    candidate: str | None = None,
    error: BaseException | None = None,
) -> dict[str, object]:
    """Build bounded, payload-free Neo4j telemetry context."""
    if stage not in _DIAGNOSTIC_STAGES:
        raise ValueError("Unsupported Neo4j diagnostic stage")
    if not math.isfinite(duration_ms):
        bounded_duration = 0.0
    else:
        bounded_duration = round(max(0.0, min(duration_ms, 3_600_000.0)), 2)
    context: dict[str, object] = {"stage": stage, "duration_ms": bounded_duration}
    if cypher is not None:
        context["query_length"] = min(len(cypher), 100_000)
        context["query_fingerprint"] = query_fingerprint(cypher)
    if candidate is not None:
        context["candidate_hash"] = query_fingerprint(candidate)
    if error is not None:
        diagnostic = classify_neo4j_error(error)
        context["neo4j_category"] = diagnostic.category
        context["neo4j_classification"] = diagnostic.classification
        if diagnostic.code is not None:
            context["neo4j_code"] = diagnostic.code
    return context


def _explain_failure_category(error: BaseException) -> ExplainFailureCategory | None:
    """Classify only known syntax/schema failures without inspecting raw text downstream."""
    if isinstance(error, Neo4jExplainError):
        return error.category
    if isinstance(
        error,
        (AuthError, ServiceUnavailable, SessionExpired, TimeoutError, ConnectionError),
    ):
        return None
    if isinstance(error, CypherSyntaxError):
        return "syntax"
    if isinstance(error, CypherTypeError):
        return "schema"
    if isinstance(error, ClientError):
        code = getattr(error, "code", "")
        if code == "Neo.ClientError.Statement.SyntaxError":
            return "syntax"
        if code in {
            "Neo.ClientError.Statement.SemanticError",
            "Neo.ClientError.Statement.EntityNotFound",
        }:
            return "schema"
    return None


@dataclass(frozen=True, slots=True)
class Neo4jReadConfig:
    uri: str
    user: str
    password: str
    database: str
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS
    uses_legacy_credentials: bool = False

    @classmethod
    def from_env(cls) -> Neo4jReadConfig:
        """Load dedicated read credentials, with an explicit legacy fallback."""

        dedicated_names = (
            "NEO4J_READ_URI",
            "NEO4J_READ_USER",
            "NEO4J_READ_PASSWORD",
        )
        dedicated = {name: os.getenv(name) for name in dedicated_names}
        if any(dedicated.values()) and not all(dedicated.values()):
            raise RuntimeError("Dedicated Neo4j read credentials must be configured together")
        uses_legacy_credentials = not all(dedicated.values())
        if uses_legacy_credentials:
            try:
                uri = os.environ["NEO4J_URI"]
                user = os.environ["NEO4J_USER"]
                password = os.environ["NEO4J_PASSWORD"]
            except KeyError as exc:
                raise RuntimeError(f"Missing required environment variable: {exc.args[0]}") from exc
        else:
            uri = str(dedicated["NEO4J_READ_URI"])
            user = str(dedicated["NEO4J_READ_USER"])
            password = str(dedicated["NEO4J_READ_PASSWORD"])
        database = (
            os.getenv("NEO4J_READ_DATABASE")
            or os.getenv("NEO4J_DATABASE")
            or DEFAULT_NEO4J_DATABASE
        )
        raw_timeout = os.getenv(
            "NEO4J_READ_QUERY_TIMEOUT_SECONDS", str(DEFAULT_QUERY_TIMEOUT_SECONDS)
        )
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise RuntimeError("NEO4J_READ_QUERY_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise RuntimeError("NEO4J_READ_QUERY_TIMEOUT_SECONDS must be positive")
        if not database.strip():
            raise RuntimeError("NEO4J_READ_DATABASE must be nonblank")
        return cls(
            uri=uri,
            user=user,
            password=password,
            database=database,
            timeout_seconds=timeout,
            uses_legacy_credentials=uses_legacy_credentials,
        )


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).upper()


def _has_schema_warning(summary: object) -> bool:
    statuses = getattr(summary, "gql_status_objects", None)
    if statuses is not None:
        for status in statuses:
            if not getattr(status, "is_notification", False):
                continue
            severity = getattr(status, "raw_severity", None) or getattr(status, "severity", "")
            classification = getattr(status, "raw_classification", None) or getattr(
                status, "classification", ""
            )
            if _enum_value(severity) == "WARNING" and _enum_value(classification) == "SCHEMA":
                return True
        return False

    notifications = getattr(summary, "summary_notifications", ())
    return any(
        _enum_value(getattr(notification, "severity_level", "")) == "WARNING"
        and _enum_value(getattr(notification, "category", "")) == "SCHEMA"
        for notification in notifications
    )


def normalize_neo4j_value(value: Any) -> Any:
    """Recursively convert Neo4j-native values into strict JSON-safe values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (Date, DateTime, Time)):
        return value.iso_format()
    if isinstance(value, Duration):
        return str(value)
    if isinstance(value, Point):
        return {
            "type": type(value).__name__,
            "coordinates": [normalize_neo4j_value(item) for item in value],
            "srid": value.srid,
        }
    if isinstance(value, (Node, Relationship)):
        return normalize_neo4j_value(dict(value.items()))
    if isinstance(value, Path):
        return {
            "nodes": normalize_neo4j_value(value.nodes),
            "relationships": normalize_neo4j_value(value.relationships),
        }
    if isinstance(value, Mapping):
        return {str(key): normalize_neo4j_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_neo4j_value(item) for item in value]
    raise Neo4jQueryError(f"Unsupported Neo4j result value type: {type(value).__name__}")


class AsyncNeo4jQueryGateway:
    """Reusable async gateway. The owner must close it or use ``async with``."""

    def __init__(self, driver: Any, config: Neo4jReadConfig, *, owns_driver: bool = False):
        self._driver = driver
        self._config = config
        self._owns_driver = owns_driver

    @classmethod
    def from_env(cls) -> AsyncNeo4jQueryGateway:
        config = Neo4jReadConfig.from_env()
        driver = AsyncGraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
        )
        return cls(driver, config, owns_driver=True)

    async def __aenter__(self) -> AsyncNeo4jQueryGateway:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_driver:
            await self._driver.close()

    async def run(
        self,
        cypher: str,
        parameters: Mapping[str, Any] | None = None,
        *,
        diagnostic_stage: DiagnosticStage = "entity_resolution",
    ) -> list[dict[str, Any]]:
        parameter_names = (
            sorted(name for name in parameters if isinstance(name, str))
            if isinstance(parameters, Mapping)
            else []
        )
        log_event(
            "neo4j_query",
            "validation_started",
            input_keys=["cypher", "parameters"],
            query_length=len(cypher),
            parameter_names=parameter_names,
            parameter_count=len(parameter_names),
        )
        try:
            guarded = guard_cypher(cypher, parameters)
        except Exception as exc:
            log_error(
                "neo4j_query",
                "validation_failed",
                exc,
                status="failed",
                guard_decision="rejected",
                query_length=len(cypher),
                parameter_names=parameter_names,
            )
            raise
        log_event(
            "neo4j_query",
            "validation_completed",
            status="success",
            guard_decision="accepted",
            read_only=True,
            query_length=len(guarded.text),
            parameter_names=sorted(guarded.parameters),
            parameter_count=len(guarded.parameters),
            query_limit=guarded.limit,
        )
        explain_started_at = time.perf_counter()
        log_event(
            "neo4j_query",
            "explain_started",
            context=neo4j_diagnostic_context(
                stage=diagnostic_stage,
                duration_ms=0,
                cypher=guarded.text,
            ),
            parameter_names=sorted(guarded.parameters),
            query_limit=guarded.limit,
            read_only=True,
        )
        try:
            explain = await self._execute(
                Query(f"EXPLAIN {guarded.text}", timeout=self._config.timeout_seconds), guarded
            )
            if getattr(explain.summary, "query_type", None) != "r":
                raise Neo4jQueryError("Neo4j did not classify the query as read-only")
            if _has_schema_warning(explain.summary):
                raise Neo4jExplainError("schema")
        except Exception as exc:
            log_event(
                "neo4j_query",
                "explain_failed",
                level="error",
                context=neo4j_diagnostic_context(
                    stage=diagnostic_stage,
                    duration_ms=(time.perf_counter() - explain_started_at) * 1000,
                    cypher=guarded.text,
                    error=exc,
                ),
                status="failed",
                parameter_names=sorted(guarded.parameters),
            )
            category = _explain_failure_category(exc)
            if category is not None:
                raise Neo4jExplainError(category, cause=exc) from exc
            raise
        log_event(
            "neo4j_query",
            "explain_completed",
            context=neo4j_diagnostic_context(
                stage=diagnostic_stage,
                duration_ms=(time.perf_counter() - explain_started_at) * 1000,
                cypher=guarded.text,
            ),
            status="success",
            query_structure=guarded.text,
            parameter_names=sorted(guarded.parameters),
            read_only=True,
        )
        execution_started_at = time.perf_counter()
        log_event(
            "neo4j_query",
            "execution_started",
            context=neo4j_diagnostic_context(
                stage=(
                    "dynamic_execution"
                    if diagnostic_stage == "dynamic_explain"
                    else diagnostic_stage
                ),
                duration_ms=0,
                cypher=guarded.text,
            ),
            parameter_names=sorted(guarded.parameters),
            read_only=True,
        )
        try:
            result = await self._execute(
                Query(guarded.text, timeout=self._config.timeout_seconds), guarded
            )
            if getattr(result.summary, "query_type", None) != "r":
                raise Neo4jQueryError("Neo4j did not classify execution as read-only")
            if _has_schema_warning(result.summary):
                raise Neo4jQueryError("Neo4j reported a schema warning during execution")
            rows = [normalize_neo4j_value(record.data()) for record in result.records]
        except Exception as exc:
            log_event(
                "neo4j_query",
                "execution_failed",
                level="error",
                context=neo4j_diagnostic_context(
                    stage="dynamic_execution"
                    if diagnostic_stage == "dynamic_explain"
                    else diagnostic_stage,
                    duration_ms=(time.perf_counter() - execution_started_at) * 1000,
                    cypher=guarded.text,
                    error=exc,
                ),
                status="failed",
                parameter_names=sorted(guarded.parameters),
            )
            raise
        log_event(
            "neo4j_query",
            "execution_completed",
            context={
                **neo4j_diagnostic_context(
                    stage="dynamic_execution"
                    if diagnostic_stage == "dynamic_explain"
                    else diagnostic_stage,
                    duration_ms=(time.perf_counter() - execution_started_at) * 1000,
                    cypher=guarded.text,
                ),
                "rows_count": len(rows),
            },
            status="success",
            query_structure=guarded.text,
            parameter_names=sorted(guarded.parameters),
            read_only=True,
        )
        return rows

    async def _execute(self, query: Query, guarded: GuardedCypher) -> Any:
        return await self._driver.execute_query(
            query,
            parameters_=guarded.parameters,
            routing_=RoutingControl.READ,
            database_=self._config.database,
        )


async def run_gateway_with_diagnostics(
    gateway: Any,
    cypher: str,
    parameters: Mapping[str, Any] | None,
    *,
    stage: DiagnosticStage,
) -> list[dict[str, Any]]:
    """Pass diagnostic stages to the production gateway while preserving test seams."""
    if isinstance(gateway, AsyncNeo4jQueryGateway):
        return await gateway.run(cypher, parameters, diagnostic_stage=stage)
    return cast(list[dict[str, Any]], await gateway.run(cypher, parameters))


@asynccontextmanager
async def open_query_gateway() -> AsyncIterator[AsyncNeo4jQueryGateway]:
    """Open and deterministically close a domain query gateway."""
    gateway = AsyncNeo4jQueryGateway.from_env()
    try:
        yield gateway
    finally:
        await gateway.close()


async def run_query(cypher: str, params: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Execute one guarded query with lifecycle-managed async access."""
    async with open_query_gateway() as gateway:
        return await gateway.run(cypher, params)
