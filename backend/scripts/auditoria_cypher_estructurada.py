#!/usr/bin/env python3
"""Run reusable read-only audits of Cypher generation through the real graph."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agente.grafo.constructor import construir_grafo
from agente.utils.cypher_guard import CypherGuardError, guard_cypher, mask_cypher_for_analysis

PREGUNTAS_AUDITORIA = (
    (
        "¿Cuáles son las 20 empresas con mayor número de ofertas publicadas dentro de la "
        "industria financiera, ordenadas de mayor a menor?"
    ),
    (
        "¿Qué herramientas aparecen en más ofertas laborales de empresas pertenecientes "
        "a la industria financiera?"
    ),
    "¿Cuáles son los 10 puestos más demandados en ofertas que requieren la herramienta Python?",
    (
        "¿Qué habilidades son más frecuentes en las ofertas para Analista de Datos y cómo "
        "se ordenan por cantidad de ofertas?"
    ),
    (
        "¿Qué industrias concentran la mayor cantidad de ofertas laborales y cuántas ofertas "
        "tiene cada una?"
    ),
    (
        "¿Qué empresas publican ofertas que requieren herramientas y habilidades, mostrando "
        "empresa, herramienta, habilidad y fecha de publicación?"
    ),
    (
        "¿Qué competencias curriculares están relacionadas con cursos de la carrera Ingeniería "
        "de Sistemas y cuáles aparecen con mayor frecuencia?"
    ),
    (
        "¿Qué empresas tienen ofertas para puestos cuyo nombre contiene Analista y cuántas "
        "ofertas publican?"
    ),
    (
        "¿Cuáles son las ofertas más recientes de empresas de la industria financiera que "
        "requieren Python o SQL?"
    ),
    (
        "¿Qué relación existe entre las herramientas requeridas por las ofertas y los puestos "
        "más demandados?"
    ),
)

PREGUNTAS_ADVERSARIALES = (
    "¿Qué industria corresponde al identificador INDU_NO_EXISTE?",
    "¿Qué herramientas corresponden a los identificadores HERR_NO_EXISTE y HERR_TAMPOCO_EXISTE?",
    "¿Qué cursos pertenecen a la carrera con identificador CAR_NO_EXISTE?",
    "¿Qué empresas pertenecen a la industria financiera?",
    "¿Cuántas ofertas requieren Python?",
    "¿Cuántas ofertas requieren Python o SQL?",
    "¿Qué puestos requieren Python y SQL?",
    "¿Qué herramientas aparecen para puestos de Analista?",
    "¿Qué habilidades se piden en ofertas para Analista de Datos?",
    "¿Qué ofertas mencionan el cargo crudo Analista en el texto publicado?",
    "¿Qué puestos formales contienen Analista en su nombre?",
    "¿Cuáles son las empresas con más ofertas durante 2025?",
    "¿Cuáles son las ofertas publicadas desde 2025-01-01 hasta 2025-12-31?",
    "¿Qué industrias tuvieron ofertas recientes y cuántas fueron?",
    "¿Qué herramientas están relacionadas con cada puesto y cuántas ofertas sostienen cada par?",
    "¿Qué combinaciones únicas de empresa, puesto y herramienta aparecen en las ofertas?",
    "¿Qué combinaciones únicas de empresa, herramienta y habilidad aparecen en las ofertas?",
    "¿Qué carreras reciben ofertas de empresas financieras?",
    "¿Qué competencias aparecen en cursos de Ingeniería de Sistemas?",
    "¿Qué empresas publicaron ofertas que requieren Pythno?",
    "¿Qué empresas pertenecen a la industria finaciera?",
    "¿Qué puestos aparecen para el término ambiguo Analista?",
    "¿Cuántas ofertas no tienen fecha de publicación?",
    "¿Qué ofertas tienen fecha de finalización posterior a su publicación?",
    "¿Qué empresas ofrecen puestos de Datos o Finanzas?",
    "¿Qué herramientas distintas requiere cada empresa?",
    "¿Qué puestos tienen más herramientas distintas asociadas?",
    "¿Qué industrias, empresas y puestos concentran más ofertas?",
)

_SENSITIVE = re.compile(
    r"(?:api[_-]?key|authorization|bearer|credential|password|passwd|secret|token|uri|dsn|database_url)",
    re.I,
)
_SECRET_TEXT = re.compile(
    r"(?i)(?:(?:neo4j(?:\+s)?|bolt(?:\+s)?|https?)://[^\s]+|"
    r"(?:password|token|secret|api[_-]?key)\s*[=:]\s*[^\s,;]+)"
)


class AsyncGraph(Protocol):
    async def ainvoke(
        self,
        state: Mapping[str, Any],
        *,
        config: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


def serializar_seguro(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _SENSITIVE.search(key):
        return "<REDACTED>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return _SECRET_TEXT.sub("<REDACTED>", value) if isinstance(value, str) else value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): serializar_seguro(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [serializar_seguro(item) for item in value]
    return _SECRET_TEXT.sub("<REDACTED>", str(value))


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def _variables_for_label(cypher: str, label: str) -> set[str]:
    return {
        match.group("variable").upper()
        for match in re.finditer(
            rf"(?i)\(\s*(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*{re.escape(label)}\b",
            cypher,
        )
    }


def _has_distinct_count_for_label(cypher: str, label: str) -> bool:
    variables = _variables_for_label(cypher, label)
    counted = {
        match.group("variable").upper()
        for match in re.finditer(
            r"(?i)\bCOUNT\s*\(\s*DISTINCT\s+"
            r"(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\s*\)",
            cypher,
        )
    }
    return bool(variables & counted)


def _return_projects_label_property(
    cypher: str,
    label: str,
    properties: set[str],
) -> bool:
    variables = _variables_for_label(cypher, label)
    return_matches = list(re.finditer(r"(?i)\bRETURN\b", cypher))
    if not variables or not return_matches:
        return False
    tail = cypher[return_matches[-1].end() :]
    boundary = re.search(r"(?i)\b(?:ORDER\s+BY|SKIP|LIMIT)\b", tail)
    return_clause = tail[: boundary.start()] if boundary else tail
    projected = {
        (match.group("variable").upper(), match.group("property").lower())
        for match in re.finditer(
            r"(?i)\b(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\."
            r"(?P<property>[A-Za-z_][A-Za-z0-9_]*)\b",
            return_clause,
        )
    }
    return any(
        variable in variables and property_name in properties
        for variable, property_name in projected
    )


def evaluar_semantica(
    question: str,
    state: Mapping[str, Any],
    rows: Sequence[object],
) -> list[str]:
    """Return stable, value-free reasons why a result is not semantically proven."""
    failures: list[str] = []
    cypher = state.get("cypher")
    parameters = state.get("parameters")
    query_limit = state.get("query_limit")
    if not isinstance(cypher, str) or not cypher.strip():
        return ["missing_cypher"]
    if not isinstance(parameters, Mapping):
        return ["invalid_parameters"]

    try:
        guarded = guard_cypher(cypher, parameters)
    except CypherGuardError as exc:
        if "Canonical ID parameter" in str(exc):
            failures.append("entity_id_property_operator_mismatch")
        else:
            failures.append("cypher_guard_rejected")
        guarded = None

    if guarded is not None and query_limit != guarded.limit:
        failures.append("query_limit_mismatch")
    if (
        isinstance(query_limit, bool)
        or not isinstance(query_limit, int)
        or not 1 <= query_limit <= 100
    ):
        failures.append("invalid_query_limit")
    elif len(rows) > query_limit:
        failures.append("rows_exceed_query_limit")

    question_normalized = _normalized_text(question)
    try:
        cypher_for_analysis = mask_cypher_for_analysis(cypher)
    except CypherGuardError:
        cypher_for_analysis = ""
    cypher_normalized = re.sub(r"\s+", " ", cypher_for_analysis).upper()
    ranking_intent = any(
        marker in question_normalized
        for marker in ("mas ", "mayor", "frecuent", "demandad", "concentran")
    ) and "mas recient" not in question_normalized
    offer_count_intent = (
        "oferta" in question_normalized
        and "herramientas distintas" not in question_normalized
    )
    if ranking_intent and offer_count_intent and "OFERTA_LABORAL" in cypher_normalized:
        if not _has_distinct_count_for_label(cypher_for_analysis, "Oferta_Laboral"):
            failures.append("offer_ranking_requires_distinct_offer_count")
    if ranking_intent and "frecuenc" in question_normalized:
        if "COUNT(DISTINCT" not in cypher_normalized.replace(" ", ""):
            failures.append("frequency_ranking_requires_distinct_count")

    formal_position_intent = "puesto" in question_normalized or re.search(
        r"\bofertas?\s+para\b", question_normalized
    )
    raw_cargo_intent = (
        "cargo crudo" in question_normalized or "texto publicado" in question_normalized
    )
    if formal_position_intent and not raw_cargo_intent:
        requires_offer_link = "oferta" in question_normalized
        if ":PUESTO" not in cypher_normalized or (
            requires_offer_link and ":OFRECE" not in cypher_normalized
        ):
            failures.append("formal_position_requires_puesto_relationship")

    if "mostrando" in question_normalized or "combinaciones unicas" in question_normalized:
        if "RETURN DISTINCT" not in cypher_normalized:
            failures.append("combination_listing_requires_return_distinct")

    if (
        "relacion" in question_normalized
        and "herramient" in question_normalized
        and "puesto" in question_normalized
    ):
        if not _return_projects_label_property(
            cypher_for_analysis, "Puesto", {"id_puesto", "nombre"}
        ):
            failures.append("position_tool_ranking_missing_position_dimension")
        if not _return_projects_label_property(
            cypher_for_analysis,
            "Herramienta",
            {"id_herramienta", "nombre_herramienta"},
        ):
            failures.append("position_tool_ranking_missing_tool_dimension")
        if not _has_distinct_count_for_label(cypher_for_analysis, "Oferta_Laboral"):
            failures.append("position_tool_ranking_requires_distinct_offer_count")

    recent_offer_listing = bool(
        re.search(
            r"\b(?:cuales son las ofertas|que ofertas)(?:\s+son)?\s+"
            r"(?:las\s+)?(?:mas\s+)?recientes?\b",
            question_normalized,
        )
    )
    if recent_offer_listing:
        if re.search(r"ORDER BY [^\n]*FECHA_PUBLICACION DESC", cypher_normalized) is None:
            failures.append("recent_offers_require_descending_publication_date")

    return list(dict.fromkeys(failures))


def proyectar_resultado(
    *,
    id: int,
    question: str,
    result: Mapping[str, Any] | None = None,
    duration_ms: float = 0.0,
    error: BaseException | None = None,
) -> dict[str, Any]:
    """Project graph state into a report with technical and semantic verdicts."""
    state = result or {}
    raw_rows = state.get("filas")
    rows = (
        list(raw_rows)
        if isinstance(raw_rows, Sequence) and not isinstance(raw_rows, (str, bytes))
        else []
    )
    state_error = state.get("error")
    technical_success = error is None and not bool(state_error)
    semantic_failures = evaluar_semantica(question, state, rows) if technical_success else []
    semantic_success = technical_success and not semantic_failures
    error_type = (
        type(error).__name__
        if error is not None
        else (type(state_error).__name__ if isinstance(state_error, BaseException) else None)
    )
    error_value = (
        _SECRET_TEXT.sub("<REDACTED>", str(error))
        if error is not None
        else (str(state_error) if state_error else None)
    )
    return {
        "id": id,
        "question": question,
        "duration_ms": round(duration_ms, 2),
        "status": "success" if semantic_success else "failed",
        "technical_success": technical_success,
        "semantic_success": semantic_success,
        "semantic_failures": semantic_failures,
        "cypher": serializar_seguro(state.get("cypher")),
        "parameters": serializar_seguro(state.get("parameters", {})),
        "query_limit": serializar_seguro(state.get("query_limit")),
        "rows_count": len(rows),
        "rows_preview": serializar_seguro(rows[:5]),
        "response": serializar_seguro(state.get("respuesta")),
        "error": serializar_seguro(error_value),
        "error_type": error_type,
    }


async def ejecutar_auditoria(
    preguntas: Sequence[str] = PREGUNTAS_AUDITORIA,
    *,
    grafo: AsyncGraph | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    graph = grafo or construir_grafo()
    results = []
    for question_id, question in enumerate(preguntas, start=1):
        started = time.perf_counter()
        try:
            state = await graph.ainvoke(
                {"pregunta": question},
                config={
                    "configurable": {
                        "thread_id": f"cypher-audit-{question_id}-{uuid4()}"
                    }
                },
            )
            entry = proyectar_resultado(
                id=question_id,
                question=question,
                result=state,
                duration_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            entry = proyectar_resultado(
                id=question_id,
                question=question,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=exc,
            )
        results.append(entry)
        print(
            f"[{question_id:02d}] {entry['status']} "
            f"technical={entry['technical_success']} semantic={entry['semantic_success']} "
            f"({entry['duration_ms']} ms)"
        )
    report = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "question_count": len(results),
        "technical_success_count": sum(item["technical_success"] for item in results),
        "semantic_success_count": sum(item["semantic_success"] for item in results),
        "results": results,
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adversarial", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    base = Path(__file__).resolve().parent
    if args.adversarial:
        preguntas = PREGUNTAS_ADVERSARIALES
        output = base / "auditoria_cypher_adversarial_resultados.json"
    else:
        preguntas = PREGUNTAS_AUDITORIA
        output = base / "auditoria_cypher_resultados.json"
    report = asyncio.run(ejecutar_auditoria(preguntas, output_path=output))
    print(
        f"Summary: technical={report['technical_success_count']}/{report['question_count']} "
        f"semantic={report['semantic_success_count']}/{report['question_count']}"
    )
    print(f"JSON: {output}")
    return 0 if report["semantic_success_count"] == report["question_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
