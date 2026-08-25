from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import pytest
from neo4j.exceptions import CypherSyntaxError

from agente.grafo.constructor import construir_grafo
from agente.grafo.plan import Plan
from agente.nodos.resuelve_entidades import resuelve_entidades
from agente.utils.cypher_guard import guard_cypher
from agente.utils.db import Neo4jExplainError
from agente.utils.entity_resolver import (
    ENTITY_CONTRACTS,
    available_entity_contracts,
    normalize_entity_text_parameters,
    reconcile_entity_parameters,
    resolve_entity,
    resolve_entity_result,
    resolve_plan_parameters,
    resolve_plan_parameters_result,
)


class FakeGateway:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((cypher, dict(parameters or {})))
        return self.rows


class CompetenciaCatalogFallbackGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((cypher, dict(parameters or {})))
        if "WHERE n." in cypher:
            return []
        return [
            {
                "entity_id": "COMP_6546a71d727fc690",
                "entity_names": ["Pensamiento cr\u00edtico"],
            }
        ]


class ExplainFailureGateway:
    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        raise Neo4jExplainError(
            "syntax",
            code="Neo.ClientError.Statement.SyntaxError",
            cause=CypherSyntaxError("KNOWN_SECRET_QUERY_PARAMETER"),
        )


class ResolverShapeGateway:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(
        self, cypher: str, parameters: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((cypher, dict(parameters or {})))
        if any(fragment in cypher for fragment in ("toString", "coalesce", "LIMIT $limit")):
            raise Neo4jExplainError(
                "syntax",
                code="Neo.ClientError.Statement.SyntaxError",
                cause=CypherSyntaxError("OLD_RESOLVER_QUERY_SHAPE"),
            )
        return self.rows


class CountingPlanner:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.calls = 0

    def invoke(self, _: object) -> Plan:
        self.calls += 1
        return self.plan


class DirectRunnable:
    async def ainvoke(self, _: object) -> object:
        return type("Message", (), {"content": "Necesito una entidad válida."})()


class GroundedRunnable:
    async def ainvoke(self, _: object) -> object:
        return type("Message", (), {"content": "Encontré 3 ofertas."})()


ALL_ENTITY_SCHEMA = {
    "node_props": {
        "Carrera": ["id_carrera", "nombre_carrera"],
        "Empresa": ["id_empresa", "nombre", "razon_social"],
        "Industria": ["id_industria", "nombre"],
        "Puesto": ["id_puesto", "nombre"],
        "Habilidad": ["id_habilidad", "nombre_habilidad"],
        "Herramienta": ["id_herramienta", "nombre_herramienta"],
        "Competencia": ["id_competencia", "nombre_competencia"],
        "Curso": ["id_curso", "nombre_curso"],
        "Facultad": ["id_facultad", "nombre_facultad"],
    },
    "rel_props": {},
    "relationships": [],
}


@pytest.mark.parametrize(
    ("parameter", "identifier", "name"),
    [
        ("empresa_id", "EMP_1", "BCP"),
        ("industria_id", "INDU_1", "Tecnología"),
        ("carrera_id", "CAR_1", "Ingeniería de Sistemas"),
        ("puesto_id", "PUE_1", "Analista de Datos"),
        ("habilidad_id", "HAB_1", "Comunicación"),
        ("herramienta_id", "HER_1", "Python"),
        ("competencia_id", "COM_1", "Pensamiento crítico"),
        ("curso_id", "CUR_1", "Bases de Datos"),
        ("facultad_id", "FAC_1", "Facultad de Ingeniería"),
    ],
)
def test_every_schema_entity_contract_resolves_exact_normalized_name(
    parameter: str,
    identifier: str,
    name: str,
) -> None:
    gateway = FakeGateway([{"entity_id": identifier, "entity_name": name}])

    result = asyncio.run(
        resolve_entity(
            parameter,
            f"  {name.upper()}  ",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is not None
    assert result.identifier == identifier
    assert result.label == ENTITY_CONTRACTS[parameter].label


def test_entity_contracts_expose_canonical_policy_and_schema_gates_optional_entities() -> None:
    contracts = available_entity_contracts(ALL_ENTITY_SCHEMA)
    without_optional = available_entity_contracts(
        {
            "node_props": {
                "Carrera": ["id_carrera", "nombre_carrera"],
            }
        }
    )

    assert set(contracts) == set(ENTITY_CONTRACTS)
    assert "curso_id" not in without_optional
    assert "facultad_id" not in without_optional
    assert ENTITY_CONTRACTS["industria_id"].canonical_prefix == "INDU_"
    assert "IND_" not in ENTITY_CONTRACTS["industria_id"].allowed_id_prefixes


def test_resolver_accepts_unique_alias_and_normalizes_accents_punctuation_and_spaces() -> None:
    gateway = FakeGateway(
        [{"entity_id": "CAR_7", "entity_name": "Ingeniería de Sistemas"}]
    )

    result = asyncio.run(
        resolve_entity(
            "carrera",
            " sistemas ",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is not None
    assert result.identifier == "CAR_7"


@pytest.mark.parametrize("candidate", ["sistemas?", "sistemas.", "SISTEMAS"])
def test_resolver_normalizes_planner_sentence_punctuation_before_lookup(
    candidate: str,
) -> None:
    gateway = FakeGateway(
        [{"entity_id": "CAR_7", "entity_names": ["Ingeniería de Sistemas"]}]
    )

    result = asyncio.run(
        resolve_entity(
            "carrera_id",
            candidate,
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is not None
    assert result.identifier == "CAR_7"
    assert gateway.calls[0][1] == {"candidate": candidate.rstrip("?!.")}


@pytest.mark.parametrize(
    ("parameter", "identifier", "name"),
    [
        ("carrera_id", "CAR_1", "Ingeniería de Sistemas"),
        ("empresa_id", "EMP_1", "Compañía Ñandú"),
        ("industria_id", "INDU_1", "Tecnología e Innovación"),
        ("puesto_id", "PUE_1", "Diseño UX"),
        ("habilidad_id", "HAB_1", "Comunicación"),
        ("herramienta_id", "HER_1", "Café"),
        ("competencia_id", "COM_1", "Pensamiento crítico"),
    ],
)
def test_confirmed_contracts_normalize_full_accented_names_with_trailing_punctuation(
    parameter: str,
    identifier: str,
    name: str,
) -> None:
    gateway = FakeGateway(
        [{"entity_id": identifier, "entity_names": [name]}]
    )

    result = asyncio.run(
        resolve_entity(
            parameter,
            f"  {name}.  ",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is not None
    assert result.identifier == identifier
    assert gateway.calls[0][1] == {"candidate": name}


def test_resolver_uses_compatible_query_shape_at_gateway_seam() -> None:
    gateway = ResolverShapeGateway(
        [{"entity_id": "CAR_7", "entity_names": ["Ingeniería de Sistemas"]}]
    )

    result = asyncio.run(
        resolve_entity(
            "carrera_id",
            "sistemas",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is not None
    assert result.identifier == "CAR_7"
    query, parameters = gateway.calls[0]
    assert "toString" not in query
    assert "coalesce" not in query
    assert "LIMIT $limit" not in query
    assert query.endswith(
        "RETURN n.id_carrera AS entity_id, [n.nombre_carrera] AS entity_names "
        "ORDER BY n.id_carrera ASC LIMIT 64"
    )
    assert "sistemas" not in query
    assert parameters == {"candidate": "sistemas"}


def test_resolver_accepts_bounded_singular_plural_name_alias() -> None:
    gateway = FakeGateway(
        [
            {
                "entity_id": "INDU_2f544767eba03474",
                "entity_names": [
                    "Fondos y sociedades de inversión y entidades financieras similares"
                ],
            }
        ]
    )

    result = asyncio.run(
        resolve_entity_result("industria_id", "financiera", query_gateway=gateway)
    )

    assert result.status == "unique"
    assert result.matches[0].identifier == "INDU_2f544767eba03474"


def test_resolver_accepts_live_herramienta_canonical_prefix() -> None:
    result = asyncio.run(
        resolve_entity_result(
            "herramienta_id",
            "Python",
            query_gateway=FakeGateway(
                [{"entity_id": "HERR_ed26022ac17e0d7b", "entity_name": "Python"}]
            ),
        )
    )

    assert result.status == "unique"
    assert result.matches[0].identifier == "HERR_ed26022ac17e0d7b"


def test_resolver_matches_empresa_alternate_name_without_matching_null_name() -> None:
    gateway = FakeGateway(
        [{"entity_id": "EMP_7", "entity_names": [None, "Banco de Prueba"]}]
    )

    result = asyncio.run(
        resolve_entity(
            "empresa_id",
            "banco de prueba",
            query_gateway=gateway,
        )
    )

    assert result is not None
    assert result.identifier == "EMP_7"


@pytest.mark.parametrize("parameter", tuple(ENTITY_CONTRACTS))
def test_every_entity_contract_has_static_safe_name_projection(
    parameter: str,
) -> None:
    contract = ENTITY_CONTRACTS[parameter]
    candidate = "Configured Alias"
    gateway = FakeGateway(
        [
            {
                "entity_id": f"{contract.canonical_prefix}1",
                "entity_names": [candidate] + [None] * (len(contract.names) - 1),
            }
        ]
    )

    result = asyncio.run(
        resolve_entity(
            parameter,
            candidate,
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is not None
    query, parameters = gateway.calls[0]
    expected_projection = (
        f"RETURN n.{contract.identifier} AS entity_id, "
        f"[{', '.join(f'n.{name}' for name in contract.names)}] AS entity_names "
        f"ORDER BY n.{contract.identifier} ASC LIMIT 64"
    )
    assert query.endswith(expected_projection)
    assert "LIMIT $limit" not in query
    assert "toString" not in query
    assert "coalesce" not in query
    assert candidate not in query
    assert parameters == {"candidate": candidate}


@pytest.mark.parametrize(
    "value",
    [
        "Ingenieria---de   Sistemas",
        "Ingeniería de Sistemas'; MATCH (n) RETURN n",
        "{}",
    ],
)
def test_resolver_fails_closed_for_malformed_or_injection_like_values(value: str) -> None:
    gateway = FakeGateway([{"entity_id": "CAR_7", "entity_name": "Ingeniería de Sistemas"}])

    result = asyncio.run(
        resolve_entity(
            "carrera_id",
            value,
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    if "MATCH" in value or value == "{}":
        assert result is None
        assert gateway.calls == []
    else:
        assert result is not None


def test_resolver_rejects_legacy_industry_prefix_instead_of_querying_as_canonical_id() -> None:
    gateway = FakeGateway([])

    result = asyncio.run(
        resolve_entity(
            "industria_id",
            "IND_1",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is None


def test_plan_parameter_resolution_canonicalizes_aliases() -> None:
    gateway = FakeGateway([{"entity_id": "CAR_7", "entity_name": "Ingeniería de Sistemas"}])

    resolved = asyncio.run(
        resolve_plan_parameters(
            {"carrera": "sistemas"},
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )
    assert resolved == {"carrera_id": "CAR_7"}


def test_resolver_matches_unaccented_competencia_text_against_catalog_fallback() -> None:
    gateway = CompetenciaCatalogFallbackGateway()

    result = asyncio.run(
        resolve_entity_result(
            "competencia_texto",
            "pensamiento critico",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result.status == "unique"
    assert result.matches[0].identifier == "COMP_6546a71d727fc690"
    assert len(gateway.calls) == 2


def test_generic_name_parameter_is_resolved_without_term_specific_replacements() -> None:
    gateway = CompetenciaCatalogFallbackGateway()
    cypher = (
        "MATCH (c:Curso)-[:TIENE]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia) "
        "WHERE toLower(co.nombre_competencia) CONTAINS toLower($texto) "
        "RETURN DISTINCT c.nombre_curso AS curso LIMIT $limite"
    )
    result = asyncio.run(
        resuelve_entidades(
            {
                "cypher": cypher,
                "parameters": {"texto": "PENSAMIENTO CRITICO", "limite": 10},
                "schema": type("Snapshot", (), {"structured": ALL_ENTITY_SCHEMA})(),
            },
            entity_gateway=gateway,
        )
    )

    assert result["error"] is None
    assert result["parameters"] == {
        "competencia_id": "COMP_6546a71d727fc690",
        "limite": 10,
    }
    assert "co.id_competencia = $competencia_id" in result["cypher"]


def test_generic_name_parameter_normalization_is_schema_driven() -> None:
    cypher = (
        "MATCH (co:Competencia) WHERE toLower(co.nombre_competencia) "
        "CONTAINS toLower($texto) RETURN co.nombre_competencia LIMIT $limite"
    )

    normalized_cypher, normalized_parameters = normalize_entity_text_parameters(
        cypher,
        {"texto": "PENSAMIENTO CRITICO", "limite": 10},
        ALL_ENTITY_SCHEMA,
    )

    assert "$competencia_texto" in normalized_cypher
    assert "$texto" not in normalized_cypher
    assert normalized_parameters == {
        "competencia_texto": "PENSAMIENTO CRITICO",
        "limite": 10,
    }


def test_reconcile_rewrites_competencia_text_to_imported_canonical_id() -> None:
    cypher, parameters = reconcile_entity_parameters(
        "MATCH (comp:Competencia) WHERE toLower(comp.nombre_competencia) "
        "CONTAINS toLower($competencia_texto) "
        "RETURN comp.nombre_competencia AS competencia LIMIT $limite",
        {"competencia_texto": "pensamiento critico", "limite": 20},
        {"competencia_id": "COMP_6546a71d727fc690", "limite": 20},
        cardinality="one",
    )

    assert "comp.id_competencia = $competencia_id" in cypher
    assert "CONTAINS" not in cypher
    assert parameters == {"competencia_id": "COMP_6546a71d727fc690", "limite": 20}
    assert guard_cypher(cypher, parameters).limit == 20


def test_reconcile_preserves_numeric_canonical_id_type() -> None:
    cypher, parameters = reconcile_entity_parameters(
        "MATCH (e:Empresa) WHERE e.id_empresa = $empresa_id "
        "RETURN e.nombre AS empresa LIMIT $limite",
        {"empresa_id": 7, "limite": 10},
        {"empresa_id": "7", "limite": 10},
        cardinality="one",
    )

    assert "$empresa_id" in cypher
    assert parameters == {"empresa_id": 7, "limite": 10}


def test_resolver_preserves_numeric_scalar_id_without_gateway_lookup() -> None:
    gateway = FakeGateway([])

    resolved = asyncio.run(
        resolve_plan_parameters(
            {"empresa_id": 7},
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert resolved == {"empresa_id": 7}
    assert gateway.calls == []


def test_resolver_preserves_numeric_id_returned_by_name_lookup() -> None:
    gateway = FakeGateway([{"entity_id": 7, "entity_names": ["BCP"]}])

    resolved = asyncio.run(
        resolve_entity(
            "empresa_id",
            "BCP",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert resolved is not None
    assert resolved.identifier == 7
    assert type(resolved.identifier) is int


def test_many_plan_resolution_preserves_numeric_id_list_without_gateway_lookup() -> None:
    gateway = FakeGateway([])

    resolved = asyncio.run(
        resolve_plan_parameters(
            {"empresa_ids": [7, 8]},
            cardinality="many",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert resolved == {"empresa_ids": [7, 8]}
    assert all(type(value) is int for value in resolved["empresa_ids"])
    assert gateway.calls == []


def test_reconcile_maps_entity_alias_to_canonical_one_parameter() -> None:
    cypher, parameters = reconcile_entity_parameters(
        "MATCH (i:Industria) WHERE i.id_industria = $industria "
        "RETURN i.nombre AS industria LIMIT $limite",
        {"industria": "financiera", "limite": 20},
        {"industria_id": "INDU_7", "limite": 20},
        cardinality="one",
    )

    assert "$industria_id" in cypher
    assert "$industria " not in cypher
    assert parameters == {"industria_id": "INDU_7", "limite": 20}


def test_reconcile_maps_entity_alias_to_canonical_many_parameter() -> None:
    cypher, parameters = reconcile_entity_parameters(
        "MATCH (h:Herramienta) WHERE h.id_herramienta IN $herramienta "
        "RETURN h.nombre_herramienta AS herramienta LIMIT $limite",
        {"herramienta": "Python", "limite": 20},
        {"herramienta_ids": ["HER_1", "HER_2"], "limite": 20},
        cardinality="many",
    )

    assert "$herramienta_ids" in cypher
    assert "$herramienta " not in cypher
    assert parameters == {
        "herramienta_ids": ["HER_1", "HER_2"],
        "limite": 20,
    }


def test_reconcile_rewrites_text_predicate_to_canonical_one_id_contract() -> None:
    cypher, parameters = reconcile_entity_parameters(
        "MATCH (i:Industria) WHERE toLower(i.nombre) CONTAINS toLower($industria) "
        "RETURN i.nombre AS industria LIMIT $limite",
        {"industria": "financiera", "limite": 20},
        {"industria_id": "INDU_7", "limite": 20},
        cardinality="one",
    )

    assert "i.id_industria = $industria_id" in cypher
    assert "CONTAINS" not in cypher
    assert parameters == {"industria_id": "INDU_7", "limite": 20}
    assert guard_cypher(cypher, parameters).limit == 20


def test_reconcile_rewrites_text_predicate_to_canonical_many_id_contract() -> None:
    cypher, parameters = reconcile_entity_parameters(
        "MATCH (h:Herramienta) WHERE h.nombre_herramienta CONTAINS $herramienta "
        "RETURN h.nombre_herramienta AS herramienta LIMIT $limite",
        {"herramienta": "Python", "limite": 20},
        {"herramienta_ids": ["HERR_1", "HERR_2"], "limite": 20},
        cardinality="many",
    )

    assert "h.id_herramienta IN $herramienta_ids" in cypher
    assert "CONTAINS" not in cypher
    assert parameters == {
        "herramienta_ids": ["HERR_1", "HERR_2"],
        "limite": 20,
    }
    assert guard_cypher(cypher, parameters).limit == 20


def test_resolver_returns_unique_schema_confirmed_entity() -> None:
    gateway = FakeGateway([{"entity_id": "EMP_1", "entity_name": "BCP"}])

    result = asyncio.run(resolve_entity("empresa_id", "BCP", query_gateway=gateway))

    assert result is not None
    assert result.identifier == "EMP_1"
    assert result.label == "Empresa"
    query, parameters = gateway.calls[0]
    assert "BCP" not in query
    assert parameters == {"candidate": "BCP"}
    assert guard_cypher(query, parameters).limit == 64


@pytest.mark.parametrize(
    ("rows", "expected_status"),
    [
        ([], "not_found"),
        ([{"entity_id": "HER_1", "entity_name": "SAP"}], "unique"),
        (
            [
                {"entity_id": "HER_1", "entity_name": "SAP"},
                {"entity_id": "HER_2", "entity_name": "SAP"},
            ],
            "multiple",
        ),
    ],
)
def test_rich_resolver_exposes_explicit_cardinality_states(
    rows: list[dict[str, Any]], expected_status: str
) -> None:
    result = asyncio.run(
        resolve_entity_result("herramienta_id", "SAP", query_gateway=FakeGateway(rows))
    )

    assert result.status == expected_status
    assert [match.identifier for match in result.matches] == [
        row["entity_id"] for row in rows
    ]


def test_rich_resolver_ignores_invalid_rows_but_keeps_valid_match() -> None:
    result = asyncio.run(
        resolve_entity_result(
            "empresa_id",
            "BCP",
            query_gateway=FakeGateway(
                [
                    {"entity_id": "EMP_1", "entity_name": "BCP"},
                    {"entity_id": "not-an-empresa-id", "entity_name": "BCP"},
                ]
            ),
        )
    )

    assert result.status == "unique"
    assert [match.identifier for match in result.matches] == ["EMP_1"]


def test_rich_resolver_rejects_invalid_canonical_id_and_non_matching_name() -> None:
    invalid_id_gateway = FakeGateway([])
    invalid_id = asyncio.run(
        resolve_entity_result(
            "industria_id", "IND_1", query_gateway=invalid_id_gateway
        )
    )
    non_matching = asyncio.run(
        resolve_entity_result(
            "empresa_id",
            "BCP",
            query_gateway=FakeGateway([{"entity_id": "EMP_1", "entity_name": "Banco"}]),
        )
    )

    assert invalid_id.status == "not_found"
    assert non_matching.status == "not_found"


def test_rich_resolver_preserves_unclassified_neo4j_errors() -> None:
    class FailingGateway:
        async def run(
            self, cypher: str, parameters: Mapping[str, Any] | None = None
        ) -> list[dict[str, Any]]:
            raise RuntimeError("neo4j transport failure")

    with pytest.raises(RuntimeError, match="neo4j transport failure"):
        asyncio.run(resolve_entity_result("empresa_id", "BCP", query_gateway=FailingGateway()))


def test_many_plan_resolution_propagates_all_ids_to_stable_plural_parameter() -> None:
    result = asyncio.run(
        resolve_plan_parameters_result(
            {"herramienta": "SAP"},
            cardinality="many",
            query_gateway=FakeGateway(
                [
                    {"entity_id": "HER_1", "entity_name": "SAP"},
                    {"entity_id": "HER_2", "entity_name": "SAP"},
                ]
            ),
        )
    )

    assert result.status == "multiple"
    assert result.parameters == {"herramienta_ids": ["HER_1", "HER_2"]}


def test_many_plan_resolution_preserves_canonical_plural_ids_without_gateway_calls() -> None:
    gateway = FakeGateway([])

    result = asyncio.run(
        resolve_plan_parameters_result(
            {"herramienta_ids": ["HER_2", "HER_1"]},
            cardinality="many",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result.status == "unique"
    assert result.parameters == {"herramienta_ids": ["HER_2", "HER_1"]}
    assert gateway.calls == []


@pytest.mark.parametrize("values", [[], ["HER_1", "not-an-id"]])
def test_many_plan_resolution_rejects_invalid_canonical_plural_ids(
    values: list[str],
) -> None:
    gateway = FakeGateway([])

    result = asyncio.run(
        resolve_plan_parameters_result(
            {"herramienta_ids": values},
            cardinality="many",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result.status == "not_found"
    assert result.parameters == {}
    assert gateway.calls == []


def test_canonical_plural_ids_require_many_cardinality() -> None:
    gateway = FakeGateway([])

    result = asyncio.run(
        resolve_plan_parameters_result(
            {"herramienta_ids": ["HER_1"]},
            cardinality="one",
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result.status == "not_found"
    assert gateway.calls == []


def test_many_wrapper_remains_scalar_compatible_and_accepts_multiple_explicitly() -> None:
    gateway = FakeGateway(
        [
            {"entity_id": "HER_1", "entity_name": "SAP"},
            {"entity_id": "HER_2", "entity_name": "SAP"},
        ]
    )

    assert asyncio.run(
        resolve_plan_parameters({"herramienta": "SAP"}, query_gateway=gateway)
    ) is None
    assert asyncio.run(
        resolve_plan_parameters(
            {"herramienta": "SAP"}, cardinality="many", query_gateway=gateway
        )
    ) == {"herramienta_ids": ["HER_1", "HER_2"]}


def test_resolver_returns_no_result_for_ambiguous_match() -> None:
    gateway = FakeGateway(
        [
            {"entity_id": "EMP_1", "entity_name": "BCP"},
            {"entity_id": "EMP_2", "entity_name": "BCP"},
        ]
    )

    result = asyncio.run(resolve_entity("empresa_id", "BCP", query_gateway=gateway))

    assert result is None


def test_resolver_returns_no_result_when_entity_is_not_found() -> None:
    gateway = FakeGateway([])

    result = asyncio.run(resolve_entity("puesto_id", "Unknown role", query_gateway=gateway))

    assert result is None


@pytest.mark.parametrize("parameter", ["curso_id", "facultad_id", "silabo_id", "cobertura_id"])
def test_resolver_returns_no_result_for_unsupported_entity_parameter(parameter: str) -> None:
    result = asyncio.run(resolve_entity(parameter, "Calculo I", query_gateway=FakeGateway([])))

    assert result is None


def test_resolver_rejects_query_shaped_input_before_gateway() -> None:
    gateway = FakeGateway([{"entity_id": "EMP_1", "entity_name": "BCP"}])

    result = asyncio.run(
        resolve_entity(
            "empresa_id",
            "BCP'; MATCH (n:Empresa) RETURN n LIMIT 1",
            query_gateway=gateway,
        )
    )

    assert result is None
    assert gateway.calls == []


def test_entity_lookup_explain_failure_logs_safe_classification_without_payload_leaks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret = "Known Secret Query Parameter"
    query = (
        "MATCH (n:Carrera) WHERE n.id_carrera = $candidate OR "
        "toLower(n.nombre_carrera) CONTAINS toLower($candidate) "
        "RETURN n.id_carrera AS entity_id, [n.nombre_carrera] AS entity_names "
        "ORDER BY n.id_carrera ASC LIMIT 64"
    )

    result = asyncio.run(
        resolve_entity(
            "carrera_id",
            secret,
            query_gateway=ExplainFailureGateway(),
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result is None
    output = capsys.readouterr().out
    assert secret not in output
    assert query not in output
    assert '"candidate":' not in output
    assert "$candidate" not in output
    assert "$limit" not in output
    events = [json.loads(line) for line in output.splitlines() if line]
    failed = next(
        event for event in events if event["event"] == "lookup_explain_failed"
    )
    context = failed["context"]
    assert context["stage"] == "entity_resolution"
    assert context["contract_label"] == "Carrera"
    assert context["parameter"] == "carrera_id"
    assert context["neo4j_code"] == "Neo.ClientError.Statement.SyntaxError"
    assert context["neo4j_category"] == "syntax"
    assert context["query_length"] > 0
    assert len(context["query_fingerprint"]) == 64
    assert len(context["candidate_hash"]) == 64


def test_resolver_rejects_short_input_before_any_fuzzy_lookup() -> None:
    gateway = FakeGateway([{"entity_id": "EMP_1", "entity_name": "SAP"}])

    result = asyncio.run(resolve_entity_result("empresa_id", "a", query_gateway=gateway))

    assert result.status == "not_found"
    assert gateway.calls == []


@pytest.mark.parametrize(
    ("parameter", "identifier", "canonical_name", "typo"),
    [
        ("carrera_id", "CAR_1", "Ingeniería de Sistemas", "Ingenieria de Sstemas"),
        ("empresa_id", "EMP_1", "Banco de Crédito", "Banco de Creditoo"),
        ("industria_id", "INDU_1", "Tecnología", "Tecnolgia"),
        ("puesto_id", "PUE_1", "Analista de Datos", "Analista de Daatos"),
        ("habilidad_id", "HAB_1", "Comunicación", "Comunicacoin"),
        ("herramienta_id", "HER_1", "Python", "Pythno"),
        ("competencia_id", "COM_1", "Pensamiento crítico", "Pensaminto critico"),
        ("curso_id", "CUR_1", "Bases de Datos", "Bases de Dtaos"),
        ("facultad_id", "FAC_1", "Facultad de Ingeniería", "Facultad de Ingenieriaa"),
    ],
)
def test_resolver_uses_conservative_fuzzy_fallback_for_one_character_typos(
    parameter: str,
    identifier: str,
    canonical_name: str,
    typo: str,
) -> None:
    gateway = FakeGateway(
        [{"entity_id": identifier, "entity_names": [canonical_name]}]
    )

    result = asyncio.run(
        resolve_entity_result(
            parameter,
            typo,
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result.status == "unique"
    assert result.matches[0].identifier == identifier
    assert len(gateway.calls) == 2
    assert all("LIMIT 64" in query for query, _ in gateway.calls)


def test_resolver_returns_multiple_for_ambiguous_fuzzy_near_collision() -> None:
    gateway = FakeGateway(
        [
            {"entity_id": "EMP_1", "entity_name": "Analista de Datos"},
            {"entity_id": "EMP_2", "entity_name": "Analista de Datoz"},
        ]
    )

    result = asyncio.run(
        resolve_entity_result(
            "empresa_id",
            "Analista de Dato",
            query_gateway=gateway,
        )
    )

    assert result.status == "multiple"
    assert {match.identifier for match in result.matches} == {"EMP_1", "EMP_2"}


def test_resolver_does_not_hide_three_exact_candidates_behind_old_limit() -> None:
    gateway = FakeGateway(
        [
            {"entity_id": "HER_3", "entity_name": "SAP"},
            {"entity_id": "HER_1", "entity_name": "SAP"},
            {"entity_id": "HER_2", "entity_name": "SAP"},
        ]
    )

    result = asyncio.run(resolve_entity_result("herramienta_id", "SAP", query_gateway=gateway))

    assert result.status == "multiple"
    assert [match.identifier for match in result.matches] == ["HER_1", "HER_2", "HER_3"]


def test_resolver_accepts_one_adjacent_transposition_in_a_long_token() -> None:
    gateway = FakeGateway(
        [{"entity_id": "HER_1", "entity_names": ["Python"]}]
    )

    result = asyncio.run(
        resolve_entity_result(
            "herramienta_id",
            "Pythno",
            query_gateway=gateway,
        )
    )

    assert result.status == "unique"
    assert [match.identifier for match in result.matches] == ["HER_1"]
    assert len(gateway.calls) == 2
    assert "LIMIT 64" in gateway.calls[0][0]


@pytest.mark.parametrize(
    "value",
    [
        "САП",  # Cyrillic homoglyphs
        "SA\u0000P",
        "SAP'; RETURN n",
        "SAP // comment",
        "SAP { injected: true }",
        "x" * 201,
    ],
)
def test_resolver_rejects_homoglyph_controls_injection_and_overlong_values(
    value: str,
) -> None:
    gateway = FakeGateway([{"entity_id": "HER_1", "entity_name": "SAP"}])

    result = asyncio.run(resolve_entity_result("herramienta_id", value, query_gateway=gateway))

    assert result.status == "not_found"
    assert gateway.calls == []


@pytest.mark.parametrize(
    ("parameter", "identifier"),
    [
        (parameter, contract.canonical_prefix + "99")
        for parameter, contract in ENTITY_CONTRACTS.items()
    ],
)
def test_canonical_ids_always_win_without_fuzzy_or_gateway_calls(
    parameter: str,
    identifier: str,
) -> None:
    gateway = FakeGateway([])

    result = asyncio.run(
        resolve_entity_result(
            parameter,
            identifier,
            query_gateway=gateway,
            schema=ALL_ENTITY_SCHEMA,
        )
    )

    assert result.status == "unique"
    assert result.matches[0].identifier == identifier
    assert gateway.calls == []


@pytest.mark.skip(reason="Entity resolution is no longer part of the active graph")
def test_fast_path_entity_miss_falls_back_to_planner() -> None:
    planner = CountingPlanner(Plan(accion="responder_directo"))
    resolver_gateway = FakeGateway([])
    graph = construir_grafo(
        planner_runnable=planner,
        direct_runnable=DirectRunnable(),
        entity_gateway=resolver_gateway,
    )

    result = asyncio.run(
        graph.ainvoke({"pregunta": "¿Cuántas ofertas publicó la empresa BCP?"})
    )

    assert result["plantilla_rapida"] is False
    assert planner.calls == 1
    assert result["respuesta"] == "Necesito una entidad válida."


@pytest.mark.skip(reason="Template and entity routes are no longer part of the active graph")
def test_planner_template_uses_unique_resolved_identifier() -> None:
    planner = CountingPlanner(
        Plan(
            accion="usar_plantilla",
            template_id="ofertas_de_empresa",
            parametros={"empresa_id": "Banco de Credito"},
        )
    )
    resolver_gateway = FakeGateway(
        [{"entity_id": "EMP_1", "entity_name": "Banco de Credito"}]
    )
    template_gateway = FakeGateway([{"total_ofertas": 3}])
    graph = construir_grafo(
        planner_runnable=planner,
        entity_gateway=resolver_gateway,
        template_gateway=template_gateway,
        grounded_runnable=GroundedRunnable(),
    )

    result = asyncio.run(
        graph.ainvoke({"pregunta": "¿Cuántas ofertas publicó Banco de Credito?"})
    )

    assert result["plan"].parametros == {"empresa_id": "EMP_1"}
    assert template_gateway.calls[0][1] == {"empresa_id": "EMP_1"}
