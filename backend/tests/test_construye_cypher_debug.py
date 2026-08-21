from __future__ import annotations

import asyncio

from langchain_core.messages import BaseMessage

from agente.nodos.construye_cypher import _debug_cypher, construye_cypher
from agente.nodos.generar_cypher import GeneratedQuery
from agente.utils.neo4j_schema import Neo4jSchemaSnapshot


def test_cypher_debug_is_disabled_by_default(
    monkeypatch, capsys
) -> None:
    monkeypatch.delenv("CIAR_DEBUG_CYPHER", raising=False)

    _debug_cypher("generated", "MATCH (n:Empresa) RETURN n.nombre LIMIT 1", {})

    assert capsys.readouterr().err == ""


def test_cypher_debug_is_enabled_only_with_explicit_flag(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CIAR_DEBUG_CYPHER", "1")

    _debug_cypher("generated", "MATCH (n:Empresa) RETURN n.nombre LIMIT 1", {})

    output = capsys.readouterr().err
    assert output.startswith("[DEBUG-CYPHER]")
    assert "stage=generated" in output
    assert "MATCH (n:Empresa) RETURN n.nombre LIMIT 1" not in output


def test_cypher_debug_ignores_other_environment_values(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CIAR_DEBUG_CYPHER", "true")

    _debug_cypher("generated", "MATCH (n:Empresa) RETURN n.nombre LIMIT 1", {})

    assert capsys.readouterr().err == ""


def test_cypher_debug_redacts_quoted_literals(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CIAR_DEBUG_CYPHER", "1")
    cypher = (
        "MATCH (n:Empresa) WHERE n.nombre = 'SAP' AND n.codigo = \"ABC\" "
        "RETURN n.nombre LIMIT 1"
    )

    _debug_cypher("schema", cypher, {})

    output = capsys.readouterr().err
    assert "SAP" not in output
    assert "ABC" not in output
    assert "MATCH" not in output
    assert "query_length=" in output


def test_cypher_debug_does_not_print_parameter_values_or_secrets(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CIAR_DEBUG_CYPHER", "1")

    _debug_cypher(
        "guard",
        "MATCH (n:Empresa) WHERE n.id_empresa = $empresa_id RETURN n.nombre LIMIT $limite",
        {"empresa_id": "private-company", "limite": 10},
    )

    output = capsys.readouterr().err
    assert "private-company" not in output
    assert "10" not in output
    assert "empresa_id:str" in output
    assert "limite:int" in output


class SequenceGenerator:
    def __init__(self, outputs: list[GeneratedQuery]) -> None:
        self.outputs = outputs
        self.calls: list[list[BaseMessage]] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> GeneratedQuery:
        self.calls.append(messages)
        return self.outputs[len(self.calls) - 1]


def test_semantic_id_mismatch_triggers_bounded_regeneration_before_neo4j() -> None:
    bad = GeneratedQuery(
        cypher=(
            "MATCH (i:Industria) WHERE toLower(i.nombre) CONTAINS "
            "toLower($industria_id) RETURN i.nombre AS industria LIMIT $limite"
        ),
        parameters={"industria_id": "INDU_1", "limite": 10},
    )
    good = GeneratedQuery(
        cypher=(
            "MATCH (i:Industria) WHERE i.id_industria = $industria_id "
            "RETURN i.nombre AS industria LIMIT $limite"
        ),
        parameters={"industria_id": "INDU_1", "limite": 10},
    )
    generator = SequenceGenerator([bad, good])
    snapshot = Neo4jSchemaSnapshot(
        text="schema",
        structured={
            "node_props": {"Industria": ["id_industria", "nombre"]},
            "rel_props": {},
            "relationships": [],
        },
    )

    result = asyncio.run(
        construye_cypher(
            {"pregunta": "Empresas de la industria financiera", "schema": snapshot},
            generated_runnable=generator,
        )
    )

    assert len(generator.calls) == 2
    assert result["cypher"] == good.cypher
    assert result["parameters"] == good.parameters
    retry_prompt = str(generator.calls[1][1].content)
    assert "contrato semántico de parámetros" in retry_prompt
    assert "CONTAINS" in retry_prompt
