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


def test_technology_follow_up_retries_when_generated_query_ignores_tool_node() -> None:
    bad = GeneratedQuery(
        cypher=(
            "MATCH (c:Curso)-[:TIENE]->(s:Silabo) "
            "WHERE toLower(c.nombre_curso) CONTAINS toLower($curso_texto) "
            "RETURN DISTINCT c.nombre_curso AS curso, s.sumilla AS contenido LIMIT $limite"
        ),
        parameters={"curso_texto": "ciberseguridad", "limite": 10},
    )
    good = GeneratedQuery(
        cypher=(
            "MATCH (c:Curso)-[:TIENE]->(s:Silabo)-[:ENSENA]->(h:Herramienta) "
            "RETURN DISTINCT h.nombre_herramienta AS tecnologia LIMIT $limite"
        ),
        parameters={"limite": 10},
    )
    generator = SequenceGenerator([bad, good])
    snapshot = Neo4jSchemaSnapshot(
        text="schema",
        structured={
            "node_props": {
                "Curso": ["id_curso", "nombre_curso"],
                "Silabo": ["sumilla"],
                "Herramienta": ["id_herramienta", "nombre_herramienta"],
            },
            "rel_props": {"TIENE": [], "ENSENA": []},
            "relationships": [
                {"start": "Curso", "type": "TIENE", "end": "Silabo"},
                {"start": "Silabo", "type": "ENSENA", "end": "Herramienta"},
            ],
        },
    )

    result = asyncio.run(
        construye_cypher(
            {
                "pregunta": "con que tecnologias se ensenan",
                "pregunta_contextualizada": (
                    "Consulta previa relevante: Ciberseguridad. "
                    "Consulta actual: con que tecnologias se ensenan"
                ),
                "schema": snapshot,
            },
            generated_runnable=generator,
        )
    )

    assert len(generator.calls) == 2
    assert result["cypher"] == good.cypher
    assert "Herramienta" in str(generator.calls[1][1].content)


def test_gap_question_retries_optional_match_that_does_not_filter_covered_tools() -> None:
    bad = GeneratedQuery(
        cypher=(
            "MATCH (o:Oferta_Laboral)-[:DIRIGE_A]->(c:Carrera) "
            "MATCH (o)-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "OPTIONAL MATCH (c)-[:ENSENIA]->(cu:Curso)-[:TIENE]->"
            "(cc:Cobertura_Curricular)-[:ENSENIA]->(hc:Herramienta) "
            "WHERE toLower(c.nombre_carrera) CONTAINS toLower($carrera) "
            "AND toLower(hc.nombre_herramienta) = toLower(h.nombre_herramienta) "
            "AND hc IS NULL "
            "RETURN h.nombre_herramienta AS herramienta, "
            "count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        parameters={"carrera": "ingenieria de sistemas", "limite": 20},
    )
    good = GeneratedQuery(
        cypher=(
            "MATCH (o:Oferta_Laboral)-[:DIRIGE_A]->(c:Carrera) "
            "MATCH (o)-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "WHERE toLower(c.nombre_carrera) CONTAINS toLower($carrera) "
            "AND h.nombre_herramienta IS NOT NULL "
            "AND size(trim(h.nombre_herramienta)) > 0 "
            "AND NOT (c)-[:ENSENIA]->(:Curso)-[:TIENE]->"
            "(:Cobertura_Curricular)-[:ENSENIA]->(h) "
            "RETURN h.nombre_herramienta AS herramienta, true AS brecha_curricular, "
            "count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        parameters={"carrera": "ingenieria de sistemas", "limite": 20},
    )
    generator = SequenceGenerator([bad, good])
    snapshot = Neo4jSchemaSnapshot(
        text="schema",
        structured={
            "node_props": {
                "Carrera": ["id_carrera", "nombre_carrera"],
                "Curso": ["id_curso", "nombre_curso"],
                "Cobertura_Curricular": ["id_cob_curricular"],
                "Oferta_Laboral": ["id_ofe_laboral"],
                "Requerimiento_Laboral": ["id_req_laboral"],
                "Herramienta": ["id_herramienta", "nombre_herramienta"],
            },
            "rel_props": {
                "DIRIGE_A": [],
                "TIENE": [],
                "REQUIERE": [],
                "ENSENIA": [],
            },
            "relationships": [
                {"start": "Oferta_Laboral", "type": "DIRIGE_A", "end": "Carrera"},
                {
                    "start": "Oferta_Laboral",
                    "type": "TIENE",
                    "end": "Requerimiento_Laboral",
                },
                {
                    "start": "Requerimiento_Laboral",
                    "type": "REQUIERE",
                    "end": "Herramienta",
                },
                {"start": "Carrera", "type": "ENSENIA", "end": "Curso"},
                {
                    "start": "Curso",
                    "type": "TIENE",
                    "end": "Cobertura_Curricular",
                },
                {
                    "start": "Cobertura_Curricular",
                    "type": "ENSENIA",
                    "end": "Herramienta",
                },
            ],
        },
    )

    result = asyncio.run(
        construye_cypher(
            {
                "pregunta": (
                    "Dime qué herramientas falta cubrir por Ingeniería de Sistemas "
                    "que el mercado laboral exija"
                ),
                "schema": snapshot,
            },
            generated_runnable=generator,
        )
    )

    assert len(generator.calls) == 2
    assert result["cypher"] == good.cypher
    retry_prompt = str(generator.calls[1][1].content)
    assert "brecha currícula-mercado" in retry_prompt
    assert "OPTIONAL MATCH" in retry_prompt
