"""Conservative static guard for the supported read-only Cypher subset.

This is intentionally not a complete Cypher parser and does not validate the
live Neo4j schema. Queries outside the small, analyzable subset fail closed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from agente.utils.entity_semantics import CANONICAL_ENTITY_PARAMETERS, canonical_id_contract

MAX_QUERY_LIMIT = 100


class CypherGuardError(ValueError):
    """Raised when a query cannot be proven safe by the static guard."""


@dataclass(frozen=True, slots=True)
class GuardedCypher:
    """A query and parameter set accepted without rewriting the query text."""

    text: str
    parameters: dict[str, Any]
    limit: int


_PARAMETER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PROPERTY_PARAMETER_COMPARISON = re.compile(
    rf"(?i)(?P<property_expr>(?:toLower\s*\(\s*)?"
    rf"(?P<variable>{_NAME})\.(?P<property>{_NAME})(?:\s*\))?)"
    rf"\s*(?P<operator>CONTAINS|IN|=)\s*"
    rf"(?P<parameter_expr>(?:toLower\s*\(\s*)?"
    rf"\$(?P<parameter>{_NAME})(?:\s*\))?)"
)
_PARAMETER_PROPERTY_EQUALITY = re.compile(
    rf"(?i)(?P<parameter_expr>(?:toLower\s*\(\s*)?"
    rf"\$(?P<parameter>{_NAME})(?:\s*\))?)\s*=\s*"
    rf"(?P<property_expr>(?:toLower\s*\(\s*)?"
    rf"(?P<variable>{_NAME})\.(?P<property>{_NAME})(?:\s*\))?)"
)
_MAP_PROPERTY_PARAMETER_EQUALITY = re.compile(
    rf"(?i)(?P<property>{_NAME})\s*:\s*\$(?P<parameter>{_NAME})"
)
_NODE_PATTERN_PROPERTY_MAP = re.compile(
    rf"(?is)\(\s*(?:{_NAME}\s*(?::{_NAME}\s*)*|(?::{_NAME}\s*)+)"
    rf"\{{(?P<properties>[^{{}}]*)\}}"
)
_WHERE_CLAUSE = re.compile(r"(?i)\bWHERE\b")
_CLAUSE_BOUNDARY = re.compile(
    r"(?i)\b(?:MATCH|OPTIONAL\s+MATCH|WITH|RETURN|UNWIND|ORDER\s+BY|SKIP|LIMIT)\b"
)
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+|[()\[\]{},.:]")
_FORBIDDEN_WORDS = frozenset(
    {
        "ALTER",
        "CALL",
        "CREATE",
        "DATABASE",
        "DELETE",
        "DENY",
        "DETACH",
        "DROP",
        "EXECUTE",
        "FINISH",
        "FOREACH",
        "GRANT",
        "INSERT",
        "LOAD",
        "MERGE",
        "PROFILE",
        "REMOVE",
        "RENAME",
        "REVOKE",
        "SET",
        "SHOW",
        "START",
        "STOP",
        "TERMINATE",
        "TRANSACTION",
        "TRANSACTIONS",
        "UNION",
        "USE",
        "YIELD",
    }
)
_READ_SOURCE_WORDS = frozenset({"MATCH", "UNWIND", "WITH"})
_RETURN_END_WORDS = frozenset({"ORDER", "SKIP", "LIMIT"})


def mask_cypher_for_analysis(text: str) -> str:
    """Mask quoted values/backtick identifiers before structural analysis.

    Semantic proofs must only use executable Cypher tokens. A quoted string,
    backtick identifier, or projection value must never impersonate a filter.
    """
    output = list(text)
    index = 0
    while index < len(text):
        char = text[index]
        if char == ";":
            raise CypherGuardError("Cypher statement separators are not allowed")
        if text.startswith("//", index) or text.startswith("/*", index):
            raise CypherGuardError("Cypher comments are not allowed")
        if char not in {"'", '"', "`"}:
            if ord(char) < 32 and char not in {"\t", "\n", "\r"}:
                raise CypherGuardError("Cypher control characters are not allowed")
            if ord(char) > 127:
                raise CypherGuardError("Non-ASCII Cypher syntax must use quoted values")
            index += 1
            continue

        delimiter = char
        output[index] = " "
        index += 1
        while index < len(text):
            output[index] = " "
            if text[index] == "\\" and delimiter != "`":
                index += 1
                if index < len(text):
                    output[index] = " "
                    index += 1
                continue
            if text[index] == delimiter:
                if index + 1 < len(text) and text[index + 1] == delimiter:
                    output[index + 1] = " "
                    index += 2
                    continue
                index += 1
                break
            index += 1
        else:
            raise CypherGuardError("Unterminated Cypher literal or identifier")
    return "".join(output)


def _where_clause_bodies(masked: str) -> list[str]:
    """Return predicate-only slices; projection expressions are excluded."""
    clauses: list[str] = []
    for where_match in _WHERE_CLAUSE.finditer(masked):
        tail = masked[where_match.end() :]
        boundary = _CLAUSE_BOUNDARY.search(tail)
        clauses.append(tail[: boundary.start()] if boundary else tail)
    return clauses


def _node_pattern_property_maps(masked: str) -> list[str]:
    """Return property-map bodies only from MATCH node-pattern clauses."""
    maps: list[str] = []
    for match_clause in re.finditer(r"(?i)\bMATCH\b", masked):
        tail = masked[match_clause.end() :]
        boundary = _CLAUSE_BOUNDARY.search(tail)
        pattern_clause = tail[: boundary.start()] if boundary else tail
        maps.extend(
            match.group("properties")
            for match in _NODE_PATTERN_PROPERTY_MAP.finditer(pattern_clause)
        )
    return maps


def _reconcile_parameters(masked: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    if any(not isinstance(name, str) for name in parameters):
        raise CypherGuardError("Cypher parameter names must be strings")
    referenced = set(_PARAMETER.findall(masked))
    supplied = set(parameters)
    missing = referenced - supplied
    unexpected = supplied - referenced
    if missing:
        raise CypherGuardError(f"Missing Cypher parameters: {', '.join(sorted(missing))}")
    if unexpected:
        raise CypherGuardError(f"Unexpected Cypher parameters: {', '.join(sorted(unexpected))}")
    return dict(parameters)


def _bounded_limit(tokens: list[str], parameters: Mapping[str, Any]) -> int:
    limit_indexes = [index for index, token in enumerate(tokens) if token == "LIMIT"]
    if len(limit_indexes) != 1:
        raise CypherGuardError("Exactly one statically analyzable LIMIT is required")
    index = limit_indexes[0]
    if index + 1 >= len(tokens) or index + 2 != len(tokens):
        raise CypherGuardError("LIMIT must be the final clause and use one literal or parameter")
    raw_limit = tokens[index + 1]
    if raw_limit.isdecimal():
        candidate: Any = int(raw_limit)
    elif raw_limit.startswith("$"):
        candidate = parameters.get(raw_limit[1:])
    else:
        raise CypherGuardError("LIMIT must use an integer literal or parameter")
    if (
        isinstance(candidate, bool)
        or not isinstance(candidate, int)
        or not 1 <= candidate <= MAX_QUERY_LIMIT
    ):
        raise CypherGuardError(f"LIMIT must be an integer between 1 and {MAX_QUERY_LIMIT}")
    return candidate


def _pattern_variables(masked: str) -> set[str]:
    node_variables = re.findall(r"\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=[:){])", masked)
    relationship_variables = re.findall(r"\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=[:\]{])", masked)
    return set(node_variables) | set(relationship_variables)


def _split_top_level(expressions: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    for index, char in enumerate(expressions):
        if char in "([{":
            depth += 1
        elif char in ")]}" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            items.append(expressions[start:index].strip())
            start = index + 1
    items.append(expressions[start:].strip())
    return items


def _reject_complete_entities(masked: str) -> None:
    variables = _pattern_variables(masked)
    if not variables:
        return
    return_match = list(re.finditer(r"\bRETURN\b", masked, flags=re.IGNORECASE))
    if not return_match:
        return
    start = return_match[-1].end()
    tail = masked[start:]
    end_match = re.search(r"\b(?:ORDER\s+BY|SKIP|LIMIT)\b", tail, flags=re.IGNORECASE)
    expressions = tail[: end_match.start()] if end_match else tail
    for expression in _split_top_level(expressions):
        normalized = re.sub(r"\s+", " ", expression).strip()
        match = re.fullmatch(
            r"(?i)(?:DISTINCT\s+)?([A-Za-z_][A-Za-z0-9_]*)(?:\s+AS\s+[A-Za-z_][A-Za-z0-9_]*)?",
            normalized,
        )
        if match and match.group(1) in variables:
            raise CypherGuardError("Returning complete node or relationship values is not allowed")


def _aggregate_calls(expression: str) -> list[str]:
    calls: list[str] = []
    for match in re.finditer(r"(?i)\b(?:avg|collect|count|max|min|sum)\s*\(", expression):
        depth = 1
        index = match.end()
        while index < len(expression) and depth:
            if expression[index] == "(":
                depth += 1
            elif expression[index] == ")":
                depth -= 1
            index += 1
        if depth == 0:
            calls.append(expression[match.start() : index])
    return calls


def validate_order_by_aggregate_projection(text: str) -> None:
    """Require ORDER BY aggregates to be projected so Neo4j can order grouped rows."""
    return_match = list(re.finditer(r"(?i)\bRETURN\b", text))
    if not return_match:
        return
    tail = text[return_match[-1].end() :]
    order_match = re.search(r"(?i)\bORDER\s+BY\b", tail)
    if order_match is None:
        return
    return_clause = tail[: order_match.start()]
    order_tail = tail[order_match.end() :]
    limit_match = re.search(r"(?i)\bLIMIT\b", order_tail)
    order_clause = order_tail[: limit_match.start()] if limit_match else order_tail
    normalized_return = re.sub(r"\s+", "", return_clause).lower()
    for aggregate in _aggregate_calls(order_clause):
        if re.sub(r"\s+", "", aggregate).lower() not in normalized_return:
            raise CypherGuardError(
                "ORDER BY aggregate expressions must be projected in RETURN with an alias"
            )


def guard_cypher(
    text: str,
    parameters: Mapping[str, Any] | None = None,
) -> GuardedCypher:
    """Validate a conservative read-only Cypher subset without rewriting it."""
    if not isinstance(text, str) or not text.strip():
        raise CypherGuardError("Cypher text must be nonblank")
    supplied = {} if parameters is None else parameters
    if not isinstance(supplied, Mapping):
        raise CypherGuardError("Cypher parameters must be a mapping")

    masked = mask_cypher_for_analysis(text)
    reconciled = _reconcile_parameters(masked, supplied)
    tokens = [match.group(0).upper() for match in _TOKEN.finditer(masked)]
    if not tokens:
        raise CypherGuardError("Cypher contains no analyzable tokens")
    forbidden = _FORBIDDEN_WORDS.intersection(tokens)
    if forbidden:
        raise CypherGuardError(f"Unsupported Cypher clause: {sorted(forbidden)[0]}")
    if not _READ_SOURCE_WORDS.intersection(tokens) or "RETURN" not in tokens:
        raise CypherGuardError("Cypher must contain a supported read source and RETURN")

    # Parameters are kept as tokens only for the narrow LIMIT proof below.
    limit_tokens = re.findall(
        r"\$[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*|\d+|[()\[\]{},.:]",
        masked,
    )
    normalized_tokens = [
        token if token.startswith("$") else token.upper() for token in limit_tokens
    ]
    limit = _bounded_limit(normalized_tokens, reconciled)
    _reject_complete_entities(masked)
    validate_order_by_aggregate_projection(masked)
    validate_parameter_cardinality(masked, reconciled)
    validate_entity_parameter_semantics(masked, reconciled)
    return GuardedCypher(text=text, parameters=reconciled, limit=limit)


def validate_parameter_cardinality(text: str, parameters: Mapping[str, Any]) -> None:
    """Reject scalar equality/list membership mismatches before Neo4j sees a query."""
    equal_parameters = set(re.findall(r"(?i)=\s*\$([A-Za-z_][A-Za-z0-9_]*)", text))
    list_parameters = set(
        re.findall(r"(?i)\bIN\s+\$([A-Za-z_][A-Za-z0-9_]*)", text)
    )
    for name in equal_parameters:
        if isinstance(parameters.get(name), (list, tuple)):
            raise CypherGuardError(f"Parameter ${name} cannot use equality with a list")
    for name in list_parameters:
        if not isinstance(parameters.get(name), (list, tuple)):
            raise CypherGuardError(f"Parameter ${name} requires IN with a list")


def validate_entity_parameter_semantics(
    text: str,
    parameters: Mapping[str, Any],
) -> None:
    """Require canonical entity IDs to use their ID property and exact operator.

    The canonical contract is naming-based and independent from parameter values:
    ``<entity>_id`` maps to ``id_<entity> =`` while ``<entity>_ids`` maps to
    ``id_<entity> IN``. Text properties and text operators are therefore never
    compatible with canonical ID parameters. Unknown ID-like names fail closed
    when used with text semantics, but remain available for non-entity metadata
    or ID-shaped schema properties such as ``id_sector`` and ``external_id``.

    ``text`` must already be masked by :func:`mask_cypher_for_analysis`. Only
    WHERE predicates and node property maps inside MATCH are accepted as proof;
    strings, RETURN expressions, and projection maps are deliberately ignored.
    """
    canonical = {
        name: contract
        for name in parameters
        if (contract := canonical_id_contract(name)) is not None
        and re.search(rf"\${re.escape(name)}\b", text)
    }
    comparisons: dict[str, list[tuple[str, str, bool]]] = {
        name: [] for name in canonical
    }
    all_comparisons: list[tuple[str, str, str, bool]] = []
    for predicate in _where_clause_bodies(text):
        for pattern in (
            _PROPERTY_PARAMETER_COMPARISON,
            _PARAMETER_PROPERTY_EQUALITY,
        ):
            for match in pattern.finditer(predicate):
                name = match.group("parameter")
                operator = match.groupdict().get("operator") or "="
                property_expr = match.groupdict().get("property_expr") or match.group("property")
                parameter_expr = match.groupdict().get("parameter_expr") or f"${name}"
                wrapped = "TOLOWER" in property_expr.upper() or "TOLOWER" in parameter_expr.upper()
                comparison = (match.group("property"), operator.upper(), wrapped)
                all_comparisons.append((name, *comparison))
                if name in comparisons:
                    comparisons[name].append(comparison)

    for property_map in _node_pattern_property_maps(text):
        for match in _MAP_PROPERTY_PARAMETER_EQUALITY.finditer(property_map):
            name = match.group("parameter")
            comparison = (match.group("property"), "=", False)
            all_comparisons.append((name, *comparison))
            if name in comparisons:
                comparisons[name].append(comparison)

    for name, (expected_property, expected_operator) in canonical.items():
        matches = comparisons[name]
        if not matches:
            raise CypherGuardError(
                f"Canonical ID parameter ${name} must be compared directly with "
                f".{expected_property} using {expected_operator}"
            )
        for property_name, operator, wrapped in matches:
            if (
                property_name != expected_property
                or operator != expected_operator
                or wrapped
            ):
                raise CypherGuardError(
                    f"Canonical ID parameter ${name} must be compared directly with "
                    f".{expected_property} using {expected_operator}"
                )

    contracts_by_property = {
        contract.id_property: contract
        for contract in CANONICAL_ENTITY_PARAMETERS.values()
    }
    polymorphic_element_properties = {
        "id_competencia",
        "id_habilidad",
        "id_herramienta",
    }
    for name, property_name, operator, wrapped in all_comparisons:
        if not (name.endswith("_id") or name.endswith("_ids")):
            continue
        property_contract = contracts_by_property.get(property_name)
        if property_contract is None:
            expected_operator = "IN" if name.endswith("_ids") else "="
            id_shaped_property = property_name.startswith("id_") or property_name.endswith("_id")
            if wrapped or operator != expected_operator or not id_shaped_property:
                raise CypherGuardError(
                    f"ID-like parameter ${name} must use {expected_operator} directly with "
                    "an ID-shaped property"
                )
            continue
        expected_parameter = (
            property_contract.parameter
            if operator == "="
            else property_contract.plural_parameter if operator == "IN" else None
        )
        is_dashboard_polymorphic_alias = (
            name == "elemento_id"
            and property_name in polymorphic_element_properties
            and operator == "="
            and not wrapped
        )
        if name != expected_parameter and not is_dashboard_polymorphic_alias:
            raise CypherGuardError(
                f"Canonical ID parameter ${property_contract.parameter} is required for "
                f".{property_name} using {operator}"
            )
