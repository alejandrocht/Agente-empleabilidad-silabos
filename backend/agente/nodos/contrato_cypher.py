"""Shared contracts and schema validation for active Cypher generation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Protocol, cast

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from agente.utils.cypher_guard import guard_cypher
from agente.utils.llm import GENERATED_QUERY_CHAT_PROFILE, build_chat_openai
from agente.utils.logger import log_event

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_NODE = re.compile(rf"\(\s*(?P<variable>{_NAME})?\s*(?::\s*(?P<label>{_NAME}))?\s*\)")
_RELATIONSHIP = re.compile(
    rf"\[\s*(?P<variable>{_NAME})?\s*:\s*(?P<type>{_NAME})\s*\]"
)
_DIRECTED_PATTERN = re.compile(
    r"(?=(?P<left>\([^()]*\))\s*(?P<left_connector><-|-)\s*"
    r"(?P<relationship>\[[^\[\]]+\])\s*(?P<right_connector>->|-)\s*"
    r"(?P<right>\([^()]*\)))"
)
_DIRECTED_TEXT_PATTERN = re.compile(
    r"(?P<left>\([^()]*\))\s*(?P<left_connector><-|-)\s*"
    r"(?P<relationship>\[[^\[\]]+\])\s*(?P<right_connector>->|-)\s*"
    r"(?P<right>\([^()]*\))"
)
_PROPERTY_REFERENCE = re.compile(rf"\b(?P<variable>{_NAME})\.(?P<property>{_NAME})\b")
_PARAMETER_NAME = re.compile(rf"^{_NAME}$")
_UNSUPPORTED_SYNTAX = re.compile(
    r"(?i)\b(?:UNWIND|UNION|CALL|YIELD|FOREACH|LOAD\s+CSV|EXISTS\s*\{|COUNT\s*\{)\b"
    r"|\[\s*\([^\]]*\)\s*\]|\[\s*[A-Za-z_]\w*\s+IN\b|\*\d*\.\."
)
_FUNCTION_NAMESPACES = frozenset({"date", "datetime", "duration", "localdatetime", "point"})


class GeneratedQuery(BaseModel):
    """Strict structured output accepted from the query-generation model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    cypher: str = Field(min_length=1)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("cypher")
    @classmethod
    def validate_cypher_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("cypher must be nonblank")
        return text

    @field_validator("parameters")
    @classmethod
    def validate_json_parameters(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if any(not _PARAMETER_NAME.fullmatch(name) for name in value):
            raise ValueError("parameter names must be valid Cypher identifiers")
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return value


class GeneratedQueryRunnable(Protocol):
    """Minimal async structured runnable contract used by the generator."""

    async def ainvoke(
        self, input: list[BaseMessage]
    ) -> GeneratedQuery | dict[str, Any]: ...


class SchemaValidationError(ValueError):
    """Raised when generated Cypher cannot be proven against the cached schema."""


def build_generated_query_runnable() -> GeneratedQueryRunnable:
    """Create the structured generator lazily using the Responses API."""
    log_event("dynamic_query", "model_configured", model_configured=True)
    model = build_chat_openai(GENERATED_QUERY_CHAT_PROFILE, constructor=ChatOpenAI)
    return cast(
        GeneratedQueryRunnable,
        model.with_structured_output(GeneratedQuery, method="function_calling"),
    )


def _property_names(entries: object) -> set[str]:
    if not isinstance(entries, list):
        return set()
    names: set[str] = set()
    for entry in entries:
        if isinstance(entry, str):
            names.add(entry)
        elif isinstance(entry, dict):
            candidate = entry.get("property")
            if isinstance(candidate, str):
                names.add(candidate)
    return names


def _schema_parts(
    structured: Mapping[str, Any],
) -> tuple[dict[str, set[str]], dict[str, set[str]], set[tuple[str, str, str]]]:
    node_props_raw = structured.get("node_props", {})
    rel_props_raw = structured.get("rel_props", {})
    relationships_raw = structured.get("relationships", [])
    if not isinstance(node_props_raw, Mapping) or not isinstance(rel_props_raw, Mapping):
        raise SchemaValidationError("Structured schema properties are invalid")

    node_props = {
        str(label): _property_names(properties)
        for label, properties in node_props_raw.items()
    }
    rel_props = {
        str(rel_type): _property_names(properties)
        for rel_type, properties in rel_props_raw.items()
    }
    triples: set[tuple[str, str, str]] = set()
    if not isinstance(relationships_raw, list):
        raise SchemaValidationError("Structured schema relationships are invalid")
    for relationship in relationships_raw:
        if not isinstance(relationship, Mapping):
            raise SchemaValidationError("Structured schema relationship is invalid")
        source = relationship.get("start")
        rel_type = relationship.get("type")
        target = relationship.get("end")
        if not all(isinstance(item, str) and item for item in (source, rel_type, target)):
            raise SchemaValidationError("Structured schema relationship is incomplete")
        assert isinstance(source, str)
        assert isinstance(rel_type, str)
        assert isinstance(target, str)
        triples.add((source, rel_type, target))
    return node_props, rel_props, triples


def summarize_schema(structured: Mapping[str, Any]) -> str:
    """Build a compact exact schema summary for the ephemeral model input."""
    node_props, rel_props, triples = _schema_parts(structured)
    payload = {
        "labels": {label: sorted(properties) for label, properties in sorted(node_props.items())},
        "relationship_types": {
            rel_type: sorted(properties) for rel_type, properties in sorted(rel_props.items())
        },
        "directed_relationships": [
            {"source": source, "type": rel_type, "target": target}
            for source, rel_type, target in sorted(triples)
        ],
    }
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _parse_node(token: str, labels_by_variable: Mapping[str, str]) -> tuple[str | None, str]:
    match = _NODE.fullmatch(token)
    if match is None:
        raise SchemaValidationError("Only simple labeled node patterns are supported")
    variable = match.group("variable")
    label = match.group("label")
    resolved_label = label or (labels_by_variable.get(variable) if variable else None)
    if resolved_label is None:
        raise SchemaValidationError("Every node pattern must have a provable label")
    return variable, resolved_label


def validate_generated_schema(
    cypher: str,
    structured: Mapping[str, Any],
) -> None:
    """Fail closed unless labels, properties, and directed triples are provable."""
    if "`" in cypher or _UNSUPPORTED_SYNTAX.search(cypher):
        raise SchemaValidationError("Generated Cypher uses unsupported syntax")
    node_props, rel_props, triples = _schema_parts(structured)

    labels_by_variable: dict[str, str] = {}
    node_matches = list(_NODE.finditer(cypher))
    if not node_matches:
        raise SchemaValidationError("Generated Cypher has no supported node pattern")
    for match in node_matches:
        variable = match.group("variable")
        label = match.group("label")
        if label is not None and label not in node_props:
            raise SchemaValidationError("Generated Cypher references an unknown label")
        if variable and label:
            previous = labels_by_variable.setdefault(variable, label)
            if previous != label:
                raise SchemaValidationError("A variable cannot use multiple labels")

    relationship_matches = list(_DIRECTED_PATTERN.finditer(cypher))
    if cypher.count("[") != len(relationship_matches) or cypher.count("]") != len(
        relationship_matches
    ):
        raise SchemaValidationError("Every relationship must be a simple directed pattern")

    relationship_types_by_variable: dict[str, str] = {}
    for match in relationship_matches:
        incoming = match.group("left_connector").strip() == "<-"
        outgoing = match.group("right_connector") == "->"
        if incoming == outgoing:
            raise SchemaValidationError("Relationship direction must be explicit and singular")
        rel_match = _RELATIONSHIP.fullmatch(match.group("relationship"))
        if rel_match is None:
            raise SchemaValidationError("Only one typed relationship per pattern is supported")
        rel_type = rel_match.group("type")
        if rel_type not in rel_props and not any(item[1] == rel_type for item in triples):
            raise SchemaValidationError("Generated Cypher references an unknown relationship type")
        rel_variable = rel_match.group("variable")
        if rel_variable:
            relationship_types_by_variable[rel_variable] = rel_type

        _, left_label = _parse_node(match.group("left"), labels_by_variable)
        _, right_label = _parse_node(match.group("right"), labels_by_variable)
        candidate = (
            (right_label, rel_type, left_label)
            if incoming
            else (left_label, rel_type, right_label)
        )
        if candidate not in triples:
            raise SchemaValidationError("Directed relationship pattern is not in the schema")

    for property_match in _PROPERTY_REFERENCE.finditer(cypher):
        variable = property_match.group("variable")
        property_name = property_match.group("property")
        if variable in _FUNCTION_NAMESPACES:
            continue
        if variable in labels_by_variable:
            if property_name not in node_props[labels_by_variable[variable]]:
                raise SchemaValidationError("Generated Cypher references an unknown node property")
            continue
        if variable in relationship_types_by_variable:
            if property_name not in rel_props.get(relationship_types_by_variable[variable], set()):
                raise SchemaValidationError(
                    "Generated Cypher references an unknown relationship property"
                )
            continue
        raise SchemaValidationError("Generated Cypher has an unbound property reference")


def _direction_neutral_query(cypher: str) -> str:
    """Normalize only supported relationship connectors for adapter comparison."""

    def replace_connectors(match: re.Match[str]) -> str:
        value = match.group(0)
        value = value.replace(match.group("left_connector"), "<LEFT_DIRECTION>", 1)
        return value.replace(match.group("right_connector"), "<RIGHT_DIRECTION>", 1)

    return _DIRECTED_TEXT_PATTERN.sub(replace_connectors, cypher)


def correct_relationship_direction(
    cypher: str,
    structured: Mapping[str, Any],
    parameters: Mapping[str, Any] | None = None,
) -> str:
    """Optionally correct a schema-proven relationship direction, and nothing else."""
    try:
        # The adapter is never allowed to turn an unsafe query into an executable one.
        guard_cypher(cypher, parameters)
        if any(delimiter in cypher for delimiter in ("'", '"', "`")):
            return cypher
        _, _, triples = _schema_parts(structured)
        if not triples or not all(
            re.fullmatch(_NAME, value) for triple in triples for value in triple
        ):
            return cypher
        from langchain_neo4j.chains.graph_qa.cypher_utils import (  # noqa: PLC0415
            CypherQueryCorrector,
            Schema,
        )

        corrector = CypherQueryCorrector(
            [Schema(source, rel_type, target) for source, rel_type, target in triples]
        )
        corrected = corrector.correct_query(cypher)
    except Exception:
        return cypher

    if not isinstance(corrected, str) or not corrected:
        return cypher
    if _direction_neutral_query(corrected) != _direction_neutral_query(cypher):
        return cypher
    return corrected
