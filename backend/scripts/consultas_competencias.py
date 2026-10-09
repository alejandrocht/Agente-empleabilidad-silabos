#!/usr/bin/env python3
"""Generate and execute conversational queries about curricular competencies."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Allow running this script directly from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("CIAR_LOG_LEVEL", "WARNING")

from agente.utils.db import open_query_gateway


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """One user-facing question and its generated read-only Cypher query."""

    key: str
    question: str
    cypher: str
    parameters: dict[str, object]


def build_queries(
    *,
    codigo: str,
    tipo: str,
    competencia: str | None,
    limit: int,
) -> list[QuerySpec]:
    """Build queries for conversational exploration of one competency."""

    parameters = {"codigo": codigo, "tipo": tipo, "limit": limit}
    code_parameters = parameters.copy()
    name_filter = ""
    if competencia:
        parameters["competencia"] = competencia
        name_filter = (
            " AND toLower(co.nombre_competencia) CONTAINS "
            "toLower($competencia)"
        )

    return [
        QuerySpec(
            key="cursos_y_silabos",
            question=f"¿En qué cursos y sílabos aparece la competencia {codigo}?",
            cypher=(
                "MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo) "
                "-[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia) "
                "WHERE co.tipo_competencia = $tipo "
                "AND co.codigo_competencia = $codigo"
                f"{name_filter} "
                "RETURN c.nombre_carrera AS carrera, "
                "cu.codigo_curso AS codigo_curso, "
                "cu.nombre_curso AS curso, "
                "s.codigo_silabo AS silabo, "
                "s.periodo_academico AS periodo, "
                "co.codigo_competencia AS codigo_competencia, "
                "co.nombre_competencia AS competencia, "
                "count(DISTINCT cc) AS coberturas "
                "ORDER BY carrera, curso, silabo "
                "LIMIT $limit"
            ),
            parameters=parameters.copy(),
        ),
        QuerySpec(
            key="temas_de_los_silabos",
            question=(
                f"¿Qué temas o sumillas tienen los sílabos donde aparece {codigo}?"
            ),
            cypher=(
                "MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo) "
                "-[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia) "
                "WHERE co.tipo_competencia = $tipo "
                "AND co.codigo_competencia = $codigo"
                f"{name_filter} "
                "RETURN c.nombre_carrera AS carrera, "
                "cu.nombre_curso AS curso, "
                "s.codigo_silabo AS silabo, "
                "s.periodo_academico AS periodo, "
                "substring(coalesce(s.sumilla, ''), 0, 400) AS tema_silabo, "
                "count(DISTINCT cc) AS coberturas "
                "ORDER BY carrera, curso, silabo "
                "LIMIT $limit"
            ),
            parameters=parameters.copy(),
        ),
        QuerySpec(
            key="resumen_por_carrera",
            question=(
                f"¿Qué carreras cubren {codigo} y en cuántos cursos y sílabos?"
            ),
            cypher=(
                "MATCH (c:Carrera)-[:ENSENIA]->(cu:Curso)-[:TIENE]->(s:Silabo) "
                "-[:DECLARA]->(cc:Cobertura_Curricular)-[:CUBRE]->(co:Competencia) "
                "WHERE co.tipo_competencia = $tipo "
                "AND co.codigo_competencia = $codigo"
                f"{name_filter} "
                "RETURN c.nombre_carrera AS carrera, "
                "count(DISTINCT cu) AS cursos, "
                "count(DISTINCT s) AS silabos, "
                "count(DISTINCT cc) AS coberturas "
                "ORDER BY cursos DESC, silabos DESC, carrera "
                "LIMIT $limit"
            ),
            parameters=parameters.copy(),
        ),
        QuerySpec(
            key="otras_competencias_en_los_mismos_silabos",
            question=(
                f"¿Qué otras competencias aparecen en los mismos sílabos que {codigo}?"
            ),
            cypher=(
                "MATCH (objetivo:Competencia)<-[:CUBRE]-(cc_objetivo:Cobertura_Curricular) "
                "<-[:DECLARA]-(s:Silabo)-[:DECLARA]->(cc:Cobertura_Curricular) "
                "-[:CUBRE]->(otra:Competencia) "
                "WHERE objetivo.tipo_competencia = $tipo "
                "AND objetivo.codigo_competencia = $codigo "
                "AND otra <> objetivo "
                "RETURN otra.tipo_competencia AS tipo, "
                "otra.codigo_competencia AS codigo, "
                "otra.nombre_competencia AS competencia, "
                "count(DISTINCT s) AS silabos_compartidos, "
                "count(DISTINCT cc) AS coberturas "
                "ORDER BY silabos_compartidos DESC, competencia "
                "LIMIT $limit"
            ),
            parameters=code_parameters,
        ),
        QuerySpec(
            key="logros_y_habilidades",
            question=(
                f"¿Qué logros y habilidades están asociados a las coberturas de {codigo}?"
            ),
            cypher=(
                "MATCH (co:Competencia)<-[:CUBRE]-(cc:Cobertura_Curricular) "
                "WHERE co.tipo_competencia = $tipo "
                "AND co.codigo_competencia = $codigo "
                "OPTIONAL MATCH (cc)-[:CUBRE]->(h:Habilidad) "
                "OPTIONAL MATCH (cc)-[:CUBRE]->(l:Logros) "
                "RETURN co.codigo_competencia AS codigo, "
                "co.nombre_competencia AS competencia, "
                "collect(DISTINCT h.nombre_habilidad) AS habilidades, "
                "collect(DISTINCT l.logro) AS logros, "
                "count(DISTINCT cc) AS coberturas "
                "LIMIT $limit"
            ),
            parameters=code_parameters,
        ),
    ]


async def execute_queries(queries: list[QuerySpec]) -> list[dict[str, object]]:
    """Execute generated queries through the guarded Neo4j read gateway."""

    results: list[dict[str, object]] = []
    async with open_query_gateway() as gateway:
        for query in queries:
            try:
                rows = await gateway.run(query.cypher, query.parameters)
                results.append(
                    {
                        "key": query.key,
                        "question": query.question,
                        "cypher": query.cypher,
                        "parameters": query.parameters,
                        "status": "ok",
                        "rows": rows,
                    }
                )
            except Exception as exc:  # pragma: no cover - live diagnostic boundary
                results.append(
                    {
                        "key": query.key,
                        "question": query.question,
                        "cypher": query.cypher,
                        "parameters": query.parameters,
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
    return results


def parse_args() -> argparse.Namespace:
    """Parse the competency exploration options."""

    parser = argparse.ArgumentParser(
        description="Genera y ejecuta consultas conversacionales de competencias."
    )
    parser.add_argument("--codigo", default="G6", help="Código de competencia, por ejemplo G6.")
    parser.add_argument(
        "--tipo",
        default="generica",
        choices=("generica", "especifica"),
        help="Tipo de competencia.",
    )
    parser.add_argument(
        "--competencia",
        default=None,
        help="Filtro opcional por nombre, por ejemplo 'Autogestión del aprendizaje'.",
    )
    parser.add_argument("--limit", type=int, default=100, help="Máximo de filas por consulta.")
    parser.add_argument(
        "--solo-generar",
        action="store_true",
        help="Muestra las consultas sin conectarse a Neo4j.",
    )
    return parser.parse_args()


def print_generated_queries(queries: list[QuerySpec]) -> None:
    """Print questions, parameters, and Cypher before execution."""

    for query in queries:
        print(f"\n### {query.key}")
        print(f"Pregunta que resuelve: {query.question}")
        print("Parámetros:")
        print(json.dumps(query.parameters, ensure_ascii=False, indent=2))
        print("Cypher:")
        print(query.cypher)


async def async_main(args: argparse.Namespace) -> None:
    """Generate, print, and optionally execute the conversational queries."""

    if args.limit < 1 or args.limit > 100:
        raise SystemExit("--limit debe estar entre 1 y 100")

    queries = build_queries(
        codigo=args.codigo,
        tipo=args.tipo,
        competencia=args.competencia,
        limit=args.limit,
    )
    print_generated_queries(queries)
    if args.solo_generar:
        return

    print("\n## Resultados Neo4j")
    for result in await execute_queries(queries):
        print(f"\n### {result['key']} — {result['status']}")
        print(f"Pregunta: {result['question']}")
        if result["status"] == "ok":
            print(json.dumps(result["rows"], ensure_ascii=False, default=str, indent=2))
        else:
            print(f"{result['error_type']}: {result['error']}")


def main() -> None:
    """Run the CLI."""

    asyncio.run(async_main(parse_args()))


if __name__ == "__main__":
    main()
