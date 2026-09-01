from __future__ import annotations

import importlib

import pytest

from agente.nodos.generar_cypher import (
    GeneratedQuery,
    build_generated_query_runnable,
    correct_relationship_direction,
    validate_generated_schema,
)

SCHEMA = {
    "node_props": {
        "Empresa": [
            {"property": "id_empresa", "type": "INTEGER"},
            {"property": "nombre", "type": "STRING"},
        ],
        "Oferta_Laboral": [
            {"property": "id_ofe_laboral", "type": "INTEGER"},
            {"property": "cargo", "type": "STRING"},
        ],
    },
    "rel_props": {"PUBLICA": []},
    "relationships": [
        {"start": "Empresa", "type": "PUBLICA", "end": "Oferta_Laboral"}
    ],
}


def test_generated_query_contract_rejects_non_json_parameters() -> None:
    with pytest.raises(ValueError):
        GeneratedQuery(
            cypher="MATCH (e:Empresa) RETURN e.nombre AS empresa LIMIT 10",
            parameters={"bad": object()},
        )


def test_corrector_changes_only_a_schema_proven_inverse_direction() -> None:
    reverse = (
        "MATCH (o:Oferta_Laboral)-[:PUBLICA]->(e:Empresa) "
        "RETURN o.cargo AS cargo LIMIT 10"
    )

    assert correct_relationship_direction(reverse, SCHEMA) == (
        "MATCH (o:Oferta_Laboral)<-[:PUBLICA]-(e:Empresa) "
        "RETURN o.cargo AS cargo LIMIT 10"
    )


def test_build_generated_runnable_uses_role_specific_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("agente.nodos.generar_cypher")
    model_calls: dict[str, object] = {}
    structured_calls: list[tuple[object, str]] = []
    expected = object()

    class FakeModel:
        def with_structured_output(self, schema: object, *, method: str) -> object:
            structured_calls.append((schema, method))
            return expected

    def fake_chat_openai(**kwargs: object) -> FakeModel:
        model_calls.update(kwargs)
        return FakeModel()

    monkeypatch.setenv("OPENAI_MODEL_GENERADOR_CYPHER", "generator-test-model")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_GENERADOR_CYPHER", "high")
    monkeypatch.setenv("OPENAI_USE_RESPONSES_API_GENERADOR_CYPHER", "true")
    monkeypatch.setattr(module, "ChatOpenAI", fake_chat_openai)

    assert build_generated_query_runnable() is expected
    assert model_calls == {
        "model": "generator-test-model",
        "temperature": 0,
        "use_responses_api": True,
        "reasoning_effort": "high",
    }
    assert structured_calls == [(GeneratedQuery, "function_calling")]


def test_schema_validator_accepts_known_reverse_written_pattern() -> None:
    validate_generated_schema(
        "MATCH (o:Oferta_Laboral)<-[:PUBLICA]-(e:Empresa) "
        "RETURN o.cargo AS cargo LIMIT 10",
        SCHEMA,
    )
