from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from scripts.auditoria_cypher_estructurada import (
    PREGUNTAS_ADVERSARIALES,
    PREGUNTAS_AUDITORIA,
    ejecutar_auditoria,
    evaluar_semantica,
    proyectar_resultado,
)


def test_projection_preserves_fields_limits_rows_and_omits_internals() -> None:
    entry = proyectar_resultado(
        id=1,
        question="Pregunta",
        duration_ms=12.345,
        result={
            "cypher": "MATCH (n:Node) RETURN n.name AS name LIMIT $limite",
            "parameters": {"limite": 20},
            "query_limit": 20,
            "filas": [{"name": str(i)} for i in range(7)],
            "respuesta": "Respuesta",
            "schema": "private",
            "trace_id": "private",
        },
    )

    assert entry["cypher"] == "MATCH (n:Node) RETURN n.name AS name LIMIT $limite"
    assert entry["parameters"] == {"limite": 20}
    assert entry["query_limit"] == 20
    assert entry["response"] == "Respuesta"
    assert entry["rows_count"] == 7
    assert entry["rows_preview"] == [{"name": str(i)} for i in range(5)]
    assert entry["technical_success"] is True
    assert entry["semantic_success"] is True
    assert "schema" not in entry and "trace_id" not in entry


def test_projection_serializes_exception_and_redacts_secret() -> None:
    entry = proyectar_resultado(
        id=2,
        question="Pregunta",
        error=RuntimeError("failed neo4j+s://user:secret@db:7687?token=abc"),
    )

    assert entry["status"] == "failed"
    assert entry["technical_success"] is False
    assert entry["semantic_success"] is False
    assert entry["error_type"] == "RuntimeError"
    assert "secret" not in entry["error"]
    assert "abc" not in entry["error"]
    assert json.loads(json.dumps(entry, ensure_ascii=False)) == entry


@pytest.mark.parametrize(
    ("cypher", "parameters"),
    [
        (
            "MATCH (i:Industria) WHERE i.nombre CONTAINS $industria_id "
            "RETURN i.nombre AS industria LIMIT 10",
            {"industria_id": "INDU_1"},
        ),
        (
            "MATCH (h:Herramienta) WHERE h.nombre_herramienta IN $herramienta_ids "
            "RETURN h.nombre_herramienta AS herramienta LIMIT 10",
            {"herramienta_ids": ["HERR_1"]},
        ),
    ],
)
def test_semantic_audit_records_id_property_operator_mismatch(
    cypher: str,
    parameters: dict[str, object],
) -> None:
    failures = evaluar_semantica(
        "Pregunta",
        {
            "cypher": cypher,
            "parameters": parameters,
            "query_limit": 10,
        },
        [],
    )

    assert "entity_id_property_operator_mismatch" in failures


def test_semantic_audit_rejects_rows_above_limit() -> None:
    failures = evaluar_semantica(
        "Pregunta",
        {
            "cypher": "MATCH (n:Node) RETURN n.name AS name LIMIT $limite",
            "parameters": {"limite": 2},
            "query_limit": 2,
        },
        [{"name": "a"}, {"name": "b"}, {"name": "c"}],
    )

    assert failures == ["rows_exceed_query_limit"]


def test_position_requirements_can_use_puesto_definition_without_offer_link() -> None:
    failures = evaluar_semantica(
        "¿Qué puestos requieren Python y SQL?",
        {
            "cypher": (
                "MATCH (p:Puesto)-[:DEFIINE]->(r:Requerimiento_Laboral)"
                "-[:REQUIERE]->(h:Herramienta) "
                "WHERE h.nombre_herramienta CONTAINS $texto "
                "RETURN DISTINCT p.nombre AS puesto LIMIT $limite"
            ),
            "parameters": {"texto": "Python", "limite": 20},
            "query_limit": 20,
        },
        [],
    )

    assert failures == []


def test_recent_industry_aggregate_can_order_by_projected_latest_date() -> None:
    failures = evaluar_semantica(
        "¿Qué industrias tuvieron ofertas recientes y cuántas fueron?",
        {
            "cypher": (
                "MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->"
                "(o:Oferta_Laboral) WHERE o.fecha_publicacion IS NOT NULL "
                "RETURN i.nombre AS industria, count(DISTINCT o) AS total_ofertas, "
                "max(o.fecha_publicacion) AS ultima_publicacion "
                "ORDER BY ultima_publicacion DESC LIMIT $limite"
            ),
            "parameters": {"limite": 20},
            "query_limit": 20,
        },
        [],
    )

    assert failures == []


@pytest.mark.parametrize("offer_variable", ["o", "oferta", "x"])
def test_offer_ranking_semantics_are_independent_from_offer_variable_name(
    offer_variable: str,
) -> None:
    failures = evaluar_semantica(
        "¿Qué empresas tienen más ofertas?",
        {
            "cypher": (
                f"MATCH (e:Empresa)-[:PUBLICA]->({offer_variable}:Oferta_Laboral) "
                f"RETURN e.nombre AS empresa, count(DISTINCT {offer_variable}) AS cantidad "
                "ORDER BY cantidad DESC LIMIT $limite"
            ),
            "parameters": {"limite": 20},
            "query_limit": 20,
        },
        [],
    )

    assert failures == []


@pytest.mark.parametrize(
    "cypher",
    [
        (
            "MATCH (o:Empresa)-[:PUBLICA]->(x:Oferta_Laboral) "
            "RETURN o.nombre AS empresa, count(DISTINCT o) AS cantidad "
            "ORDER BY cantidad DESC LIMIT $limite"
        ),
        (
            "MATCH (e:Empresa)-[:PUBLICA]->(x:Oferta_Laboral) "
            "RETURN e.nombre AS empresa, 'count(DISTINCT x)' AS proof, count(e) AS cantidad "
            "ORDER BY cantidad DESC LIMIT $limite"
        ),
    ],
)
def test_offer_ranking_rejects_distinct_count_pattern_that_does_not_count_offers(
    cypher: str,
) -> None:
    failures = evaluar_semantica(
        "¿Qué empresas tienen más ofertas?",
        {
            "cypher": cypher,
            "parameters": {"limite": 20},
            "query_limit": 20,
        },
        [],
    )

    assert "offer_ranking_requires_distinct_offer_count" in failures


def test_position_tool_semantics_are_independent_from_variables_and_return_aliases() -> None:
    failures = evaluar_semantica(
        "¿Qué relación existe entre las herramientas requeridas por las ofertas "
        "y los puestos más demandados?",
        {
            "cypher": (
                "MATCH (oferta:Oferta_Laboral)-[:OFRECE]->(posicion:Puesto) "
                "MATCH (oferta)-[:TIENE]->(:Requerimiento_Laboral)-[:REQUIERE]->"
                "(tool:Herramienta) "
                "RETURN posicion.nombre AS rol, tool.nombre_herramienta AS tecnologia, "
                "count(DISTINCT oferta) AS cantidad ORDER BY cantidad DESC LIMIT $limite"
            ),
            "parameters": {"limite": 20},
            "query_limit": 20,
        },
        [],
    )

    assert failures == []


def test_position_tool_semantics_reject_expected_alias_on_wrong_dimension() -> None:
    failures = evaluar_semantica(
        "¿Qué relación existe entre las herramientas requeridas por las ofertas "
        "y los puestos más demandados?",
        {
            "cypher": (
                "MATCH (o:Oferta_Laboral)<-[:PUBLICA]-(e:Empresa) "
                "MATCH (o)-[:TIENE]->(:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
                "RETURN e.nombre AS puesto, h.nombre_herramienta AS herramienta, "
                "count(DISTINCT o) AS total_ofertas "
                "ORDER BY total_ofertas DESC LIMIT $limite"
            ),
            "parameters": {"limite": 20},
            "query_limit": 20,
        },
        [],
    )

    assert "position_tool_ranking_missing_position_dimension" in failures


class FakeGraph:
    def __init__(self) -> None:
        self.calls = []

    async def ainvoke(self, state, *, config):
        self.calls.append((state, config))
        if len(self.calls) == 2:
            raise ValueError("bad token=hidden")
        return {
            "cypher": "MATCH (n:Node) RETURN n.name AS name LIMIT $limite",
            "parameters": {"limite": 20},
            "query_limit": 20,
            "filas": [{"name": "ok"}],
            "respuesta": "ok",
        }


def test_audit_continues_after_failure_without_real_dependencies() -> None:
    graph = FakeGraph()
    report = asyncio.run(
        ejecutar_auditoria(("Pregunta uno", "Pregunta dos", "Pregunta tres"), grafo=graph)
    )

    assert report["question_count"] == 3
    assert [item["status"] for item in report["results"]] == [
        "success",
        "failed",
        "success",
    ]
    assert len(graph.calls) == 3


VALID_TEN_RESULTS = (
    {
        "cypher": (
            "MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
            "WHERE i.id_industria = $industria_id "
            "RETURN e.nombre AS empresa, count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"industria_id": "INDU_1", "limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)"
            "-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "WHERE i.id_industria = $industria_id "
            "RETURN h.nombre_herramienta AS herramienta, count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"industria_id": "INDU_1", "limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (o:Oferta_Laboral)-[:OFRECE]->(p:Puesto) "
            "MATCH (o)-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "WHERE h.id_herramienta = $herramienta_id "
            "RETURN p.nombre AS puesto, count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"herramienta_id": "HERR_1", "limite": 10},
        "query_limit": 10,
    },
    {
        "cypher": (
            "MATCH (o:Oferta_Laboral)-[:OFRECE]->(p:Puesto) "
            "MATCH (o)-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Habilidad) "
            "WHERE p.nombre CONTAINS $puesto_texto "
            "RETURN h.nombre_habilidad AS habilidad, count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"puesto_texto": "Analista de Datos", "limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral) "
            "RETURN i.nombre AS industria, count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)-[:TIENE]->"
            "(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "MATCH (r)-[:REQUIERE]->(s:Habilidad) "
            "RETURN DISTINCT e.nombre AS empresa, h.nombre_herramienta AS herramienta, "
            "s.nombre_habilidad AS habilidad, o.fecha_publicacion AS fecha_publicacion "
            "ORDER BY fecha_publicacion DESC LIMIT $limite"
        ),
        "parameters": {"limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(cc:Cobertura_Curricular)"
            "-[:CUBRE]->(co:Competencia) WHERE c.id_carrera = $carrera_id "
            "RETURN co.nombre_competencia AS competencia, count(DISTINCT cu) AS total_cursos "
            "ORDER BY total_cursos DESC LIMIT $limite"
        ),
        "parameters": {"carrera_id": "CAR_1", "limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)-[:OFRECE]->(p:Puesto) "
            "WHERE p.nombre CONTAINS $texto "
            "RETURN e.nombre AS empresa, count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"texto": "Analista", "limite": 20},
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (i:Industria)-[:AGRUPA]->(e:Empresa)-[:PUBLICA]->(o:Oferta_Laboral)"
            "-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "WHERE i.id_industria = $industria_id AND "
            "(h.nombre_herramienta CONTAINS $python OR h.nombre_herramienta CONTAINS $sql) "
            "RETURN DISTINCT o.id_ofe_laboral AS oferta_id, "
            "o.fecha_publicacion AS fecha_publicacion "
            "ORDER BY o.fecha_publicacion DESC LIMIT $limite"
        ),
        "parameters": {
            "industria_id": "INDU_1",
            "python": "Python",
            "sql": "SQL",
            "limite": 20,
        },
        "query_limit": 20,
    },
    {
        "cypher": (
            "MATCH (o:Oferta_Laboral)-[:OFRECE]->(p:Puesto) "
            "MATCH (o)-[:TIENE]->(r:Requerimiento_Laboral)-[:REQUIERE]->(h:Herramienta) "
            "RETURN p.id_puesto AS puesto_id, p.nombre AS puesto, "
            "h.id_herramienta AS herramienta_id, h.nombre_herramienta AS herramienta, "
            "count(DISTINCT o) AS total_ofertas "
            "ORDER BY total_ofertas DESC LIMIT $limite"
        ),
        "parameters": {"limite": 20},
        "query_limit": 20,
    },
)


class TenQuestionGraph:
    def __init__(self) -> None:
        self.index = 0

    async def ainvoke(self, state, *, config):
        del state, config
        result = dict(VALID_TEN_RESULTS[self.index])
        self.index += 1
        return {**result, "filas": [], "respuesta": "ok"}


def test_all_ten_audit_questions_have_semantically_valid_flow_regressions() -> None:
    report = asyncio.run(
        ejecutar_auditoria(PREGUNTAS_AUDITORIA, grafo=TenQuestionGraph())
    )

    assert report["technical_success_count"] == 10
    assert report["semantic_success_count"] == 10
    assert all(item["status"] == "success" for item in report["results"])


def test_adversarial_battery_has_at_least_twenty_varied_questions() -> None:
    assert len(PREGUNTAS_ADVERSARIALES) >= 20
    normalized = " ".join(PREGUNTAS_ADVERSARIALES).lower()
    for marker in (
        "identificador",
        "python o sql",
        "pythno",
        "ambiguo",
        "fecha",
        "combinaciones",
        "industria",
        "herramienta",
        "carrera",
        "puesto",
        "empresa",
    ):
        assert marker in normalized


def test_adversarial_report_records_technical_and_semantic_success_per_question() -> None:
    report_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "auditoria_cypher_adversarial_resultados.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["question_count"] == len(PREGUNTAS_ADVERSARIALES) == 28
    assert report["technical_success_count"] == len(PREGUNTAS_ADVERSARIALES)
    assert report["semantic_success_count"] == len(PREGUNTAS_ADVERSARIALES)
    assert len(report["results"]) == len(PREGUNTAS_ADVERSARIALES)
    for result in report["results"]:
        assert result["status"] == "success"
        assert result["technical_success"] is True
        assert result["semantic_success"] is True
        assert result["semantic_failures"] == []
