"""Schema-backed, fail-closed resolution for user-addressable graph entities.

The repository contract confirms the seven employment entities declared below.
``Curso`` and ``Facultad`` are enabled only when an injected or live schema
contains their label, identifier, and name properties. Labels such as
``Silabo`` and ``Cobertura`` remain deferred until that contract is confirmed.
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal, Protocol

from neo4j.exceptions import ClientError, CypherSyntaxError, CypherTypeError

from agente.utils.cypher_guard import guard_cypher
from agente.utils.db import (
    Neo4jExplainError,
    neo4j_diagnostic_context,
    open_query_gateway,
    run_gateway_with_diagnostics,
)
from agente.utils.entity_semantics import CANONICAL_ENTITY_PARAMETERS
from agente.utils.logger import log_event

MAX_ENTITY_QUERY_TEXT_LENGTH = 200
ENTITY_MATCH_LIMIT = 64
MIN_ENTITY_QUERY_LENGTH = 2
FUZZY_MIN_QUERY_LENGTH = 3
FUZZY_MIN_SCORE = 0.88
FUZZY_MIN_MARGIN = 0.08
_IDENTIFIER_SUFFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")
_UNSAFE_ENTITY_TEXT = re.compile(r"(?:;|//|/\*|\*/|`|\{|\}|\\)")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_SURROUNDING_SENTENCE_PUNCTUATION = ".,!?\u00a1\u00bf\u2026"
_IDENTIFIER_SHAPED_TEXT = re.compile(r"^[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_-]+$")
_CYPHER_PARAMETER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_CYPHER_NAME = r"[A-Za-z_][A-Za-z0-9_]*"


class EntityResolutionGateway(Protocol):
    """Minimal async gateway used by the resolver and its public tests."""

    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class EntityContract:
    """Schema-backed policy for one user-addressable entity."""

    parameter: str
    label: str
    identifier: str
    names: tuple[str, ...]
    parameter_aliases: tuple[str, ...]
    allowed_id_prefixes: tuple[str, ...]
    canonical_prefix: str
    supported_relationships: tuple[str, ...]
    optional_schema_entity: bool = False

    @property
    def canonical_id_property(self) -> str:
        """Expose the contract terminology used by schema and planner audits."""
        return self.identifier

    @property
    def name_properties(self) -> tuple[str, ...]:
        """Expose all alternative schema name properties."""
        return self.names

    @property
    def supported_relationship_use(self) -> tuple[str, ...]:
        """Expose the relationship allow-list associated with this entity."""
        return self.supported_relationships


@dataclass(frozen=True, slots=True)
class EntityResolution:
    """One graph entity selected by a deterministic exact or fuzzy-safe lookup."""

    parameter: str
    label: str
    identifier: str | int
    name: str | None


ResolutionStatus = Literal["unique", "multiple", "not_found"]


@dataclass(frozen=True, slots=True)
class EntityResolutionResult:
    """Deterministic entity lookup result, including safe ambiguity."""

    status: ResolutionStatus
    parameter: str
    label: str | None
    matches: tuple[EntityResolution, ...] = ()


@dataclass(frozen=True, slots=True)
class ParameterResolutionResult:
    """Resolved plan parameters and the aggregate entity-resolution status."""

    status: ResolutionStatus
    parameters: dict[str, Any]


ENTITY_CONTRACTS: Mapping[str, EntityContract] = {
    "carrera_id": EntityContract(
        parameter="carrera_id",
        label="Carrera",
        identifier="id_carrera",
        names=("nombre_carrera",),
        parameter_aliases=("carrera_id", "carrera", "career_id", "career"),
        allowed_id_prefixes=("CAR_",),
        canonical_prefix="CAR_",
        supported_relationships=("DIRIGE_A",),
    ),
    "empresa_id": EntityContract(
        parameter="empresa_id",
        label="Empresa",
        identifier="id_empresa",
        names=("nombre", "razon_social"),
        parameter_aliases=("empresa_id", "empresa", "company_id", "company"),
        allowed_id_prefixes=("EMP_",),
        canonical_prefix="EMP_",
        supported_relationships=("AGRUPA", "PUBLICA"),
    ),
    "industria_id": EntityContract(
        parameter="industria_id",
        label="Industria",
        identifier="id_industria",
        names=("nombre",),
        parameter_aliases=("industria_id", "industria", "industry_id", "industry"),
        allowed_id_prefixes=("INDU_",),
        canonical_prefix="INDU_",
        supported_relationships=("AGRUPA",),
    ),
    "puesto_id": EntityContract(
        parameter="puesto_id",
        label="Puesto",
        identifier="id_puesto",
        names=("nombre",),
        parameter_aliases=("puesto_id", "puesto", "role_id", "role"),
        allowed_id_prefixes=("PUE_",),
        canonical_prefix="PUE_",
        supported_relationships=("OFRECE", "DEFIINE"),
    ),
    "habilidad_id": EntityContract(
        parameter="habilidad_id",
        label="Habilidad",
        identifier="id_habilidad",
        names=("nombre_habilidad",),
        parameter_aliases=("habilidad_id", "habilidad", "skill_id", "skill"),
        allowed_id_prefixes=("HAB_",),
        canonical_prefix="HAB_",
        supported_relationships=("REQUIERE",),
    ),
    "herramienta_id": EntityContract(
        parameter="herramienta_id",
        label="Herramienta",
        identifier="id_herramienta",
        names=("nombre_herramienta",),
        parameter_aliases=(
            "herramienta_id",
            "herramienta",
            "tool_id",
            "tool",
        ),
        allowed_id_prefixes=("HER_", "HERR_"),
        canonical_prefix="HER_",
        supported_relationships=("REQUIERE",),
    ),
    "competencia_id": EntityContract(
        parameter="competencia_id",
        label="Competencia",
        identifier="id_competencia",
        names=("nombre_competencia",),
        parameter_aliases=(
            "competencia_id",
            "competencia",
            "competencia_texto",
            "competency_id",
            "competency",
        ),
        allowed_id_prefixes=("COMP_", "COM_"),
        canonical_prefix="COMP_",
        supported_relationships=("REQUIERE",),
    ),
    "curso_id": EntityContract(
        parameter="curso_id",
        label="Curso",
        identifier="id_curso",
        names=("nombre_curso",),
        parameter_aliases=("curso_id", "curso", "course_id", "course"),
        allowed_id_prefixes=("CUR_",),
        canonical_prefix="CUR_",
        supported_relationships=("ENSENIA", "TIENE"),
        optional_schema_entity=True,
    ),
    "facultad_id": EntityContract(
        parameter="facultad_id",
        label="Facultad",
        identifier="id_facultad",
        names=("nombre_facultad",),
        parameter_aliases=("facultad_id", "facultad", "faculty_id", "faculty"),
        allowed_id_prefixes=("FAC_",),
        canonical_prefix="FAC_",
        supported_relationships=(),
        optional_schema_entity=True,
    ),
}

for _parameter, _semantic_contract in CANONICAL_ENTITY_PARAMETERS.items():
    _resolver_contract = ENTITY_CONTRACTS[_parameter]
    if _resolver_contract.identifier != _semantic_contract.id_property:
        raise RuntimeError(f"Entity semantic contract drift for {_parameter}")

DEFERRED_ENTITY_LABELS = (
    "Silabo",
    "Cobertura",
    "Cobertura_Curricular",
)
_CONFIRMED_WITHOUT_RUNTIME_SCHEMA = frozenset(
    parameter
    for parameter, contract in ENTITY_CONTRACTS.items()
    if not contract.optional_schema_entity
)


def _schema_properties(schema: Mapping[str, Any]) -> Mapping[str, set[str]]:
    raw_nodes = schema.get("node_props", {})
    if not isinstance(raw_nodes, Mapping):
        return {}
    properties: dict[str, set[str]] = {}
    for label, entries in raw_nodes.items():
        if not isinstance(label, str) or not isinstance(entries, list):
            continue
        values: set[str] = set()
        for entry in entries:
            if isinstance(entry, str):
                values.add(entry)
            elif isinstance(entry, Mapping) and isinstance(entry.get("property"), str):
                values.add(entry["property"])
        properties[label] = values
    return properties


def available_entity_contracts(
    schema: Mapping[str, Any] | None = None,
) -> Mapping[str, EntityContract]:
    """Return contracts confirmed by the static or supplied runtime schema."""
    if schema is None:
        return {
            parameter: contract
            for parameter, contract in ENTITY_CONTRACTS.items()
            if parameter in _CONFIRMED_WITHOUT_RUNTIME_SCHEMA
        }

    properties = _schema_properties(schema)
    return {
        parameter: contract
        for parameter, contract in ENTITY_CONTRACTS.items()
        if contract.label in properties
        and contract.identifier in properties[contract.label]
        and any(name in properties[contract.label] for name in contract.names)
    }


def normalize_entity_text_parameters(
    cypher: str,
    parameters: Mapping[str, Any],
    schema: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Route a generic name search through the matching canonical entity parameter.

    The generated query may use ``$texto`` for a single entity name property.
    Route that value through the entity resolver so matching can fold case,
    accents, punctuation, and whitespace without term-specific replacements.
    Ambiguous queries are left untouched and remain subject to normal validation.
    """
    if "$texto" not in cypher or "texto" not in parameters:
        return cypher, dict(parameters)

    predicate_region = re.split(r"\bRETURN\b", cypher, maxsplit=1, flags=re.IGNORECASE)[0]
    candidates: list[EntityContract] = []
    for contract in available_entity_contracts(schema).values():
        label_pattern = rf":{re.escape(contract.label)}\b"
        if not re.search(label_pattern, predicate_region):
            continue
        if not any(
            re.search(
                rf"\b{_CYPHER_NAME}\.{re.escape(name)}\b.*\$texto\b",
                predicate_region,
            )
            for name in contract.names
        ):
            continue
        candidates.append(contract)

    if len(candidates) != 1:
        return cypher, dict(parameters)

    contract = candidates[0]
    text_parameter = f"{contract.parameter.removesuffix('_id')}_texto"
    if text_parameter in parameters:
        return cypher, dict(parameters)

    normalized_cypher = re.sub(r"\$texto\b", f"${text_parameter}", cypher)
    normalized_parameters = dict(parameters)
    normalized_parameters[text_parameter] = normalized_parameters.pop("texto")
    return normalized_cypher, normalized_parameters


def _contract_for_parameter(
    parameter: str,
    schema: Mapping[str, Any] | None,
) -> EntityContract | None:
    return next(
        (
            contract
            for contract in available_entity_contracts(schema).values()
            if parameter in contract.parameter_aliases
        ),
        None,
    )


def _candidate_text(value: Any) -> str | None:
    """Accept bounded display names and IDs, but reject query-shaped input."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    candidate = str(value).strip()
    if (
        not candidate
        or len(candidate) > MAX_ENTITY_QUERY_TEXT_LENGTH
        or _CONTROL_CHARACTER.search(candidate)
        or _UNSAFE_ENTITY_TEXT.search(candidate)
    ):
        return None
    return candidate


def _normalize_display_candidate(candidate: str) -> str | None:
    """Normalize harmless sentence punctuation without changing name content."""
    normalized = re.sub(r"\s+", " ", candidate).strip()
    normalized = normalized.strip(_SURROUNDING_SENTENCE_PUNCTUATION).strip()
    return normalized or None


def _normalized_text(value: str) -> str:
    """Fold case, accents, punctuation, and whitespace for exact token matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def _singular_token(token: str) -> str:
    """Normalize the bounded singular/plural variation used by graph names."""
    if len(token) > 5 and token.endswith("es"):
        return token[:-2]
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _equivalent_name_tokens(left: str, right: str) -> bool:
    return left == right or _singular_token(left) == _singular_token(right)


def _matches_singular_plural_name(candidate: str, names: tuple[str, ...]) -> bool:
    candidate_tokens = _normalized_text(candidate).split()
    if not candidate_tokens:
        return False
    return any(
        all(
            any(
                _equivalent_name_tokens(candidate_token, name_token)
                for name_token in name_tokens
            )
            for candidate_token in candidate_tokens
        )
        and candidate_tokens != name_tokens
        for name_tokens in (_normalized_text(name).split() for name in names)
    )


def _contains_non_latin_text(value: str) -> bool:
    """Reject homoglyphs and opaque Unicode controls before any database call."""
    decomposed = unicodedata.normalize("NFKD", value)
    return any(
        ord(character) > 127 and not unicodedata.combining(character)
        for character in decomposed
    )


def _looks_like_identifier(value: str) -> bool:
    """Keep ID-shaped input out of the fuzzy name matcher."""
    return value.isdecimal() or bool(_IDENTIFIER_SHAPED_TEXT.fullmatch(value))


def _is_canonical_identifier(contract: EntityContract, value: str) -> bool:
    """Apply the contract's ID format, including the canonical industry prefix."""
    if value.isdecimal():
        return True
    for prefix in contract.allowed_id_prefixes:
        if value.startswith(prefix) and _IDENTIFIER_SUFFIX.fullmatch(value[len(prefix) :]):
            return True
    return False


def _identifier_sort_key(value: str | int) -> tuple[int, str]:
    """Sort mixed primitive IDs deterministically without coercing stored values."""
    return (0 if isinstance(value, int) else 1, str(value))


def _resolution_query(contract: EntityContract) -> str:
    """Build a static query from the schema allow-list, never from user input."""
    name_conditions = " OR ".join(
        f"toLower(n.{name}) CONTAINS toLower($candidate)"
        for name in contract.names
    )
    name_projection = ", ".join(f"n.{name}" for name in contract.names)
    return (
        f"MATCH (n:{contract.label}) "
        f"WHERE n.{contract.identifier} = $candidate OR {name_conditions} "
        f"RETURN n.{contract.identifier} AS entity_id, "
        f"[{name_projection}] AS entity_names "
        f"ORDER BY n.{contract.identifier} ASC LIMIT {ENTITY_MATCH_LIMIT}"
    )


def _catalog_query(contract: EntityContract) -> str:
    """Return a deterministic, bounded catalog for the Python fuzzy fallback."""
    name_projection = ", ".join(f"n.{name}" for name in contract.names)
    return (
        f"MATCH (n:{contract.label}) "
        f"RETURN n.{contract.identifier} AS entity_id, "
        f"[{name_projection}] AS entity_names "
        f"ORDER BY n.{contract.identifier} ASC LIMIT {ENTITY_MATCH_LIMIT}"
    )


def _row_names(row: Mapping[str, Any]) -> tuple[str, ...]:
    if "entity_names" in row:
        raw_names = row.get("entity_names")
        if not isinstance(raw_names, (list, tuple)):
            return ()
        return tuple(
            name.strip() for name in raw_names if isinstance(name, str) and name.strip()
        )
    name = row.get("entity_name")
    return (name.strip(),) if isinstance(name, str) and name.strip() else ()


def _is_resolver_explain_failure(error: BaseException) -> bool:
    """Recognize only EXPLAIN syntax/schema failures at the resolver boundary."""
    if isinstance(error, Neo4jExplainError):
        return error.category in {"syntax", "schema"}
    if isinstance(error, (CypherSyntaxError, CypherTypeError)):
        return True
    return isinstance(error, ClientError) and getattr(error, "code", None) in {
        "Neo.ClientError.Statement.SyntaxError",
        "Neo.ClientError.Statement.SemanticError",
        "Neo.ClientError.Statement.EntityNotFound",
    }


def _matches_name(candidate: str, names: tuple[str, ...]) -> bool:
    """Allow exact names or complete name-token aliases, never partial fuzzy text."""
    candidate_tokens = _normalized_text(candidate).split()
    if not candidate_tokens:
        return False
    for name in names:
        name_tokens = _normalized_text(name).split()
        if candidate_tokens == name_tokens:
            return True
        if all(token in name_tokens for token in candidate_tokens):
            return True
    return False


def _name_match_kind(candidate: str, names: tuple[str, ...]) -> int:
    """Rank exact normalized names above complete token aliases."""
    candidate_normalized = _normalized_text(candidate)
    candidate_tokens = candidate_normalized.split()
    if not candidate_tokens:
        return 0
    best = 0
    for name in names:
        name_normalized = _normalized_text(name)
        name_tokens = name_normalized.split()
        if candidate_normalized == name_normalized:
            best = max(best, 2)
        elif all(token in name_tokens for token in candidate_tokens):
            best = max(best, 1)
    return best


def _valid_resolution_row(
    row: object,
    contract: EntityContract,
    candidate: str,
) -> EntityResolution | None:
    if not isinstance(row, Mapping):
        return None
    resolution = _resolution_from_row(row, contract)
    if resolution is None:
        return None
    if resolution.name is not None and not _matches_name(candidate, _row_names(row)):
        return None
    return resolution


def _resolution_from_row(
    row: object,
    contract: EntityContract,
) -> EntityResolution | None:
    if not isinstance(row, Mapping):
        return None
    identifier = row.get("entity_id")
    if isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
        return None
    identifier_text = str(identifier).strip()
    if not identifier_text or not _is_canonical_identifier(contract, identifier_text):
        return None
    preserved_identifier = identifier if isinstance(identifier, int) else identifier_text
    names = _row_names(row)
    return EntityResolution(
        parameter=contract.parameter,
        label=contract.label,
        identifier=preserved_identifier,
        name=names[0] if names else None,
    )


def _fuzzy_score(candidate: str, resolution: EntityResolution, names: tuple[str, ...]) -> float:
    """Score only display names; identifiers never enter this function."""
    candidate_normalized = _normalized_text(candidate)
    return max(
        (
            SequenceMatcher(None, candidate_normalized, _normalized_text(name)).ratio()
            for name in names
            if _normalized_text(name)
        ),
        default=0.0,
    )


def _has_single_adjacent_transposition(candidate: str, name: str) -> bool:
    """Recognize one adjacent character swap in one sufficiently long token."""
    candidate_tokens = _normalized_text(candidate).split()
    name_tokens = _normalized_text(name).split()
    if len(candidate_tokens) != len(name_tokens):
        return False

    differing_tokens = [
        (candidate_token, name_token)
        for candidate_token, name_token in zip(candidate_tokens, name_tokens)
        if candidate_token != name_token
    ]
    if len(differing_tokens) != 1:
        return False

    candidate_token, name_token = differing_tokens[0]
    if len(candidate_token) != len(name_token) or len(candidate_token) < 4:
        return False
    return any(
        candidate_token[:index]
        + candidate_token[index + 1]
        + candidate_token[index]
        + candidate_token[index + 2 :]
        == name_token
        for index in range(len(candidate_token) - 1)
    )


def _fuzzy_result(
    candidate: str,
    rows: Sequence[object],
    contract: EntityContract,
) -> EntityResolutionResult:
    """Return a unique fuzzy match only when its score and margin are strong."""
    normalized_candidate = _normalized_text(candidate)
    if (
        _looks_like_identifier(candidate)
        or len(normalized_candidate.replace(" ", "")) < FUZZY_MIN_QUERY_LENGTH
    ):
        return EntityResolutionResult("not_found", contract.parameter, contract.label)

    scored: list[tuple[float, EntityResolution]] = []
    seen: set[str | int] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        resolution = _resolution_from_row(row, contract)
        if resolution is None or resolution.identifier in seen:
            continue
        seen.add(resolution.identifier)
        names = _row_names(row)
        score = _fuzzy_score(candidate, resolution, names)
        if _matches_singular_plural_name(candidate, names):
            score = max(score, FUZZY_MIN_SCORE)
        if any(_has_single_adjacent_transposition(candidate, name) for name in names):
            # Keep the global threshold unchanged: only this exact, bounded
            # edit pattern receives the existing minimum fuzzy score.
            score = max(score, FUZZY_MIN_SCORE)
        if score >= FUZZY_MIN_SCORE:
            scored.append((score, resolution))
    scored.sort(key=lambda item: (-item[0], _identifier_sort_key(item[1].identifier)))
    if not scored:
        return EntityResolutionResult("not_found", contract.parameter, contract.label)
    if len(scored) > 1 and scored[0][0] - scored[1][0] < FUZZY_MIN_MARGIN:
        ambiguous = tuple(item[1] for item in scored[:ENTITY_MATCH_LIMIT])
        return EntityResolutionResult("multiple", contract.parameter, contract.label, ambiguous)
    return EntityResolutionResult("unique", contract.parameter, contract.label, (scored[0][1],))


async def resolve_entity(
    parameter: str,
    value: Any,
    *,
    query_gateway: EntityResolutionGateway | None = None,
    schema: Mapping[str, Any] | None = None,
) -> EntityResolution | None:
    """Compatibility wrapper returning only a unique match."""
    result = await resolve_entity_result(
        parameter,
        value,
        query_gateway=query_gateway,
        schema=schema,
    )
    return result.matches[0] if result.status == "unique" else None


async def resolve_entity_result(
    parameter: str,
    value: Any,
    *,
    query_gateway: EntityResolutionGateway | None = None,
    schema: Mapping[str, Any] | None = None,
) -> EntityResolutionResult:
    """Resolve an entity while preserving unique, multiple, and not-found states."""
    contract = _contract_for_parameter(parameter, schema)
    candidate = _candidate_text(value)
    if contract is None or candidate is None:
        return EntityResolutionResult("not_found", parameter, contract.label if contract else None)
    if _is_canonical_identifier(contract, candidate):
        identifier = value if isinstance(value, int) and not isinstance(value, bool) else candidate
        match = EntityResolution(contract.parameter, contract.label, identifier, None)
        return EntityResolutionResult("unique", contract.parameter, contract.label, (match,))
    if _looks_like_identifier(candidate):
        return EntityResolutionResult("not_found", contract.parameter, contract.label)
    normalized_candidate = _normalize_display_candidate(candidate)
    if normalized_candidate is None or _contains_non_latin_text(normalized_candidate):
        return EntityResolutionResult("not_found", contract.parameter, contract.label)
    normalized_length = len(_normalized_text(normalized_candidate).replace(" ", ""))
    if normalized_length < MIN_ENTITY_QUERY_LENGTH:
        return EntityResolutionResult("not_found", contract.parameter, contract.label)

    cypher = _resolution_query(contract)
    catalog_cypher = _catalog_query(contract)
    try:
        guard_cypher(cypher, {"candidate": normalized_candidate})
        guard_cypher(catalog_cypher, {})
    except ValueError:
        return EntityResolutionResult("not_found", contract.parameter, contract.label)

    async def deterministic(
        gateway: EntityResolutionGateway, lookup_candidate: str
    ) -> EntityResolutionResult:
        async def lookup(
            lookup_cypher: str,
            lookup_parameters: Mapping[str, Any],
        ) -> list[dict[str, Any]]:
            lookup_guarded = guard_cypher(lookup_cypher, lookup_parameters)
            lookup_started_at = time.perf_counter()
            log_event(
                "entity_resolution",
                "lookup_started",
                context={
                    "contract_label": contract.label,
                    "parameter": contract.parameter,
                    **neo4j_diagnostic_context(
                        stage="entity_resolution",
                        duration_ms=0,
                        cypher=lookup_guarded.text,
                        candidate=lookup_candidate,
                    ),
                },
            )
            try:
                rows = await run_gateway_with_diagnostics(
                    gateway,
                    lookup_guarded.text,
                    lookup_guarded.parameters,
                    stage="entity_resolution",
                )
            except Exception as exc:
                if not _is_resolver_explain_failure(exc):
                    raise
                log_event(
                    "entity_resolution",
                    "lookup_explain_failed",
                    level="error",
                    context={
                        "contract_label": contract.label,
                        "parameter": contract.parameter,
                        **neo4j_diagnostic_context(
                            stage="entity_resolution",
                            duration_ms=(time.perf_counter() - lookup_started_at) * 1000,
                            cypher=lookup_guarded.text,
                            candidate=lookup_candidate,
                            error=exc,
                        ),
                    },
                )
                return []
            log_event(
                "entity_resolution",
                "lookup_completed",
                context={
                    "contract_label": contract.label,
                    "parameter": contract.parameter,
                    **neo4j_diagnostic_context(
                        stage="entity_resolution",
                        duration_ms=(time.perf_counter() - lookup_started_at) * 1000,
                        cypher=lookup_guarded.text,
                        candidate=lookup_candidate,
                    ),
                },
            )
            return rows

        rows = await lookup(cypher, {"candidate": lookup_candidate})
        exact_matches: list[tuple[int, EntityResolution]] = []
        seen: set[str | int] = set()
        for row in rows:
            resolution = _valid_resolution_row(row, contract, lookup_candidate)
            if resolution is None or resolution.identifier in seen:
                continue
            seen.add(resolution.identifier)
            exact_matches.append((_name_match_kind(lookup_candidate, _row_names(row)), resolution))
        exact_matches.sort(
            key=lambda item: (-item[0], _identifier_sort_key(item[1].identifier))
        )
        if exact_matches and exact_matches[0][0] > 0:
            matches = tuple(item[1] for item in exact_matches)
            status: ResolutionStatus = "unique" if len(matches) == 1 else "multiple"
            return EntityResolutionResult(status, contract.parameter, contract.label, matches)

        catalog_rows = await lookup(catalog_cypher, {})
        exact_catalog_matches: list[tuple[int, EntityResolution]] = []
        catalog_seen: set[str | int] = set()
        for row in catalog_rows:
            resolution = _resolution_from_row(row, contract)
            if resolution is None or resolution.identifier in catalog_seen:
                continue
            catalog_seen.add(resolution.identifier)
            match_kind = _name_match_kind(lookup_candidate, _row_names(row))
            if match_kind:
                exact_catalog_matches.append((match_kind, resolution))
        exact_catalog_matches.sort(
            key=lambda item: (-item[0], _identifier_sort_key(item[1].identifier))
        )
        if exact_catalog_matches:
            matches = tuple(item[1] for item in exact_catalog_matches)
            status = "unique" if len(matches) == 1 else "multiple"
            return EntityResolutionResult(status, contract.parameter, contract.label, matches)

        return _fuzzy_result(lookup_candidate, catalog_rows, contract)

    async def run(gateway: EntityResolutionGateway) -> EntityResolutionResult:
        return await deterministic(gateway, normalized_candidate)

    if query_gateway is not None:
        return await run(query_gateway)

    async with open_query_gateway() as gateway:
        return await run(gateway)


def _plural_entity_parameter(parameter: str) -> str:
    return f"{parameter.removesuffix('_id')}_ids"


def _entity_parameter_aliases(
    contract: EntityContract,
    cardinality: Literal["one", "many"],
) -> dict[str, str]:
    """Build the trusted alias-to-canonical parameter map for one cardinality."""
    canonical = (
        contract.parameter
        if cardinality == "one"
        else _plural_entity_parameter(contract.parameter)
    )
    aliases = set(contract.parameter_aliases)
    if cardinality == "many":
        aliases.update(
            _plural_entity_parameter(alias.removesuffix("_id") + "_id")
            for alias in contract.parameter_aliases
        )
    return {alias: canonical for alias in aliases}


def _semantically_equal_parameter_values(left: Any, right: Any) -> bool:
    """Compare JSON parameter values without erasing their caller-facing types."""
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return False
        return len(left) == len(right) and all(
            _semantically_equal_parameter_values(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right or str(left) == str(right)


def _reconcile_entity_predicate(
    cypher: str,
    *,
    source_parameter: str,
    target_parameter: str,
    contract: EntityContract,
    cardinality: Literal["one", "many"],
) -> str:
    """Rewrite one complete entity comparison to its canonical ID contract."""
    property_token = rf"{_CYPHER_NAME}\.{_CYPHER_NAME}"
    property_expression = rf"(?:toLower\s*\(\s*{property_token}\s*\)|{property_token})"
    parameter_expression = (
        rf"(?:toLower\s*\(\s*\${re.escape(source_parameter)}\s*\)"
        rf"|\${re.escape(source_parameter)}\b)"
    )
    comparison = re.compile(
        rf"(?i)(?P<property>{property_expression})\s*"
        rf"(?:CONTAINS|IN|=)\s*(?P<parameter>{parameter_expression})"
    )
    operator = "=" if cardinality == "one" else "IN"

    def replace(match: re.Match[str]) -> str:
        variable_match = re.search(
            rf"(?i)(?P<variable>{_CYPHER_NAME})\.{_CYPHER_NAME}",
            match.group("property"),
        )
        if variable_match is None:
            return match.group(0)
        variable = variable_match.group("variable")
        return f"{variable}.{contract.identifier} {operator} ${target_parameter}"

    return comparison.sub(replace, cypher)


def reconcile_entity_parameters(
    cypher: str,
    generated_parameters: Mapping[str, Any],
    resolved_parameters: Mapping[str, Any],
    *,
    cardinality: Literal["one", "many"],
) -> tuple[str, dict[str, Any]]:
    """Reconcile generated entity placeholders with trusted canonical values.

    Replacement is performed on complete Cypher parameter tokens only. The
    generated value for an entity alias is discarded in favour of the resolver's
    canonical value; all other generated parameters remain unchanged.
    """
    if cardinality not in {"one", "many"}:
        raise ValueError("cardinality must be 'one' or 'many'")
    if not isinstance(cypher, str):
        raise TypeError("cypher must be a string")

    aliases: dict[str, str] = {}
    for contract in ENTITY_CONTRACTS.values():
        for alias, canonical in _entity_parameter_aliases(contract, cardinality).items():
            previous = aliases.get(alias)
            if previous is not None and previous != canonical:
                raise ValueError(f"Ambiguous entity parameter alias: {alias}")
            aliases[alias] = canonical

    referenced = set(_CYPHER_PARAMETER.findall(cypher))
    replacements = {
        name: aliases[name]
        for name in referenced
        if (
            name in aliases
            and name != aliases[name]
            and aliases[name] in resolved_parameters
        )
    }
    reconciled_cypher = cypher
    contracts_by_alias = {
        alias: contract
        for contract in ENTITY_CONTRACTS.values()
        for alias in _entity_parameter_aliases(contract, cardinality)
    }
    for alias, canonical in replacements.items():
        reconciled_cypher = _reconcile_entity_predicate(
            reconciled_cypher,
            source_parameter=alias,
            target_parameter=canonical,
            contract=contracts_by_alias[alias],
            cardinality=cardinality,
        )
    reconciled_cypher = _CYPHER_PARAMETER.sub(
        lambda match: f"${replacements.get(match.group(1), match.group(1))}",
        reconciled_cypher,
    )
    reconciled_parameters = dict(generated_parameters)
    for alias, canonical in replacements.items():
        generated_value = reconciled_parameters.get(alias)
        reconciled_parameters.pop(alias, None)
        trusted_value = resolved_parameters[canonical]
        reconciled_parameters[canonical] = (
            generated_value
            if generated_value is not None
            and _semantically_equal_parameter_values(generated_value, trusted_value)
            else trusted_value
        )
    return reconciled_cypher, reconciled_parameters


def _contract_for_plural_parameter(
    parameter: str,
    available: Mapping[str, EntityContract],
) -> EntityContract | None:
    return next(
        (
            contract
            for contract in available.values()
            if _plural_entity_parameter(contract.parameter) == parameter
        ),
        None,
    )


def _canonical_id_list(
    value: Any,
    contract: EntityContract,
) -> list[str | int] | None:
    """Validate an already-resolved bounded list without any database lookup."""
    if not isinstance(value, (list, tuple)) or not value or len(value) > ENTITY_MATCH_LIMIT:
        return None

    canonical_ids: list[str | int] = []
    for item in value:
        candidate = _candidate_text(item)
        if candidate is None or not _is_canonical_identifier(contract, candidate):
            return None
        canonical_ids.append(
            item if isinstance(item, int) and not isinstance(item, bool) else candidate
        )
    return canonical_ids


async def resolve_plan_parameters_result(
    parameters: Mapping[str, Any],
    *,
    cardinality: Literal["one", "many"] = "one",
    query_gateway: EntityResolutionGateway | None = None,
    schema: Mapping[str, Any] | None = None,
) -> ParameterResolutionResult:
    """Resolve plan aliases, retaining all matches only for an explicit many intent."""
    available = available_entity_contracts(schema)
    resolved: dict[str, Any] = {}
    entity_seen: set[str] = set()
    aggregate_status: ResolutionStatus = "unique"
    for parameter, value in parameters.items():
        plural_contract = _contract_for_plural_parameter(parameter, available)
        if plural_contract is not None:
            if cardinality != "many":
                return ParameterResolutionResult("not_found", {})
            canonical_ids = _canonical_id_list(value, plural_contract)
            if canonical_ids is None or plural_contract.parameter in entity_seen:
                return ParameterResolutionResult("not_found", {})
            entity_seen.add(plural_contract.parameter)
            resolved[parameter] = canonical_ids
            continue

        contract = next(
            (item for item in available.values() if parameter in item.parameter_aliases),
            None,
        )
        if contract is None:
            if parameter.endswith("_id") or parameter.endswith("_ids"):
                return ParameterResolutionResult("not_found", {})
            resolved[parameter] = value
            continue
        if contract.parameter in entity_seen:
            return ParameterResolutionResult("not_found", {})
        entity_seen.add(contract.parameter)
        entity = await resolve_entity_result(
            parameter,
            value,
            query_gateway=query_gateway,
            schema=schema,
        )
        if entity.status == "not_found":
            return ParameterResolutionResult("not_found", {})
        if entity.status == "multiple":
            aggregate_status = "multiple"
            if cardinality == "one":
                return ParameterResolutionResult("multiple", {})
            resolved[_plural_entity_parameter(contract.parameter)] = [
                match.identifier for match in entity.matches
            ]
            continue
        if cardinality == "many":
            resolved[_plural_entity_parameter(contract.parameter)] = [
                entity.matches[0].identifier
            ]
        else:
            resolved[contract.parameter] = entity.matches[0].identifier

    return ParameterResolutionResult(aggregate_status, resolved)


async def resolve_plan_parameters(
    parameters: Mapping[str, Any],
    *,
    cardinality: Literal["one", "many"] = "one",
    query_gateway: EntityResolutionGateway | None = None,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compatibility wrapper returning parameters only when resolution is usable."""
    result = await resolve_plan_parameters_result(
        parameters,
        cardinality=cardinality,
        query_gateway=query_gateway,
        schema=schema,
    )
    if result.status == "not_found" or (result.status == "multiple" and cardinality == "one"):
        return None
    return result.parameters


async def resolve_template_parameters(
    parameters: Mapping[str, Any],
    *,
    query_gateway: EntityResolutionGateway | None = None,
    schema: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Hydrate confirmed entity parameters without guessing unsupported values."""
    return await resolve_plan_parameters(
        parameters,
        cardinality="one",
        query_gateway=query_gateway,
        schema=schema,
    )


async def resolve_template_parameters_result(
    parameters: Mapping[str, Any],
    *,
    query_gateway: EntityResolutionGateway | None = None,
    schema: Mapping[str, Any] | None = None,
) -> ParameterResolutionResult:
    """Return rich scalar template resolution without enabling implicit lists."""
    return await resolve_plan_parameters_result(
        parameters,
        cardinality="one",
        query_gateway=query_gateway,
        schema=schema,
    )
