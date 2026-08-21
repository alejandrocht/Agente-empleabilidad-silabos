"""Typed dashboard service over the active read-only Neo4j gateway."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from agente.cache.consultas import QueryResultCache, get_process_query_result_cache
from agente.dashboard.consultas import (
    DASHBOARD_QUERIES,
    DIMENSIONS,
    SUPPORTED_DATASETS,
    UNSUPPORTED_DATASETS,
    get_dashboard_query,
)
from agente.nodos.ejecutar_plantilla import TemplateQueryGateway
from agente.utils.cypher_guard import guard_cypher
from agente.utils.db import normalize_neo4j_value, open_query_gateway

MAX_LIMITE = 25
MAX_DIAS_RANGO = 3660
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")


class ErrorDashboard(ValueError):
    """Safe client error for invalid filters or unsupported dashboard input."""


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value.strip()) is None:
        raise ErrorDashboard(f"{name} must be a valid identifier.")
    return value.strip()


def _limit(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_LIMITE:
        raise ErrorDashboard(f"limit must be between 1 and {MAX_LIMITE}.")
    return value


def _period(desde: date, hasta: date) -> dict[str, str]:
    if desde > hasta:
        raise ErrorDashboard("The start date cannot be after the end date.")
    if (hasta - desde).days > MAX_DIAS_RANGO:
        raise ErrorDashboard("The dashboard period cannot exceed ten years.")
    return {"desde": desde.isoformat(), "hasta": (hasta + timedelta(days=1)).isoformat()}


def _dimension(slug: str) -> str:
    if slug not in DIMENSIONS:
        raise ErrorDashboard("Unsupported dashboard dimension.")
    return slug


def _validate_parameters(query_id: str, parameters: Mapping[str, Any]) -> dict[str, Any]:
    query = get_dashboard_query(query_id)
    supplied = set(parameters)
    expected = set(query.required_parameters)
    if supplied != expected:
        missing = sorted(expected - supplied)
        unexpected = sorted(supplied - expected)
        detail = []
        if missing:
            detail.append(f"missing: {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected: {', '.join(unexpected)}")
        raise ErrorDashboard("Invalid dashboard query parameters (" + "; ".join(detail) + ").")

    normalized = dict(parameters)
    for name in ("carrera_id", "elemento_id"):
        if name in normalized:
            normalized[name] = _identifier(normalized[name], name)
    if "limite" in normalized:
        normalized["limite"] = _limit(normalized["limite"])
    for name in ("desde", "hasta"):
        if name in normalized and not isinstance(normalized[name], str):
            raise ErrorDashboard(f"{name} must be an ISO date.")
    return normalized


async def _execute(
    query_id: str,
    parameters: Mapping[str, Any],
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> list[dict[str, Any]]:
    """Execute one immutable query after static read-only validation."""
    normalized_parameters = _validate_parameters(query_id, parameters)
    query = get_dashboard_query(query_id)
    guarded = guard_cypher(query.cypher, normalized_parameters)
    cache = result_cache or get_process_query_result_cache()
    cached = cache.get(guarded)
    if cached is not None:
        return cached

    async def run(gateway: TemplateQueryGateway) -> list[dict[str, Any]]:
        rows = await gateway.run(guarded.text, guarded.parameters)
        normalized = normalize_neo4j_value(rows)
        if not isinstance(normalized, list) or not all(isinstance(row, dict) for row in normalized):
            raise TypeError("Dashboard gateway returned an invalid row collection")
        bounded = normalized[: guarded.limit]
        cache.put(guarded, bounded)
        return bounded

    if query_gateway is not None:
        return await run(query_gateway)
    async with open_query_gateway() as gateway:
        return await run(gateway)


async def listar_carreras(
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    rows = await _execute(
        "dashboard_carreras", {}, query_gateway=query_gateway, result_cache=result_cache
    )
    return {
        "carreras": [
            {
                "id": str(row["id"]),
                "nombre": str(row["nombre"]),
                "cursos_conectados": int(row.get("cursos_conectados") or 0),
                "cobertura_disponible": int(row.get("cursos_conectados") or 0) > 0,
            }
            for row in rows
        ]
    }


async def metadatos(
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    rows = await _execute(
        "dashboard_rango_ofertas", {}, query_gateway=query_gateway, result_cache=result_cache
    )
    row = rows[0] if rows else {}
    return {
        "periodo_disponible": {
            "desde": str(row["desde"])[:10] if row.get("desde") is not None else None,
            "hasta": str(row["hasta"])[:10] if row.get("hasta") is not None else None,
        },
        "dimensiones": [
            {"id": slug, "nombre": label} for slug, (label, _, _) in DIMENSIONS.items()
        ],
        "datasets": {
            "supported": list(SUPPORTED_DATASETS),
            "unsupported": dict(UNSUPPORTED_DATASETS),
        },
    }


async def obtener_carrera(
    carrera_id: str,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    rows = await _execute(
        "dashboard_carrera",
        {"carrera_id": carrera_id},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    if not rows:
        raise ErrorDashboard("The selected career does not exist.")
    row = rows[0]
    courses = int(row.get("cursos_conectados") or 0)
    return {
        "id": str(row["id"]),
        "nombre": str(row["nombre"]),
        "cursos_conectados": courses,
        "cobertura_disponible": courses > 0,
    }


async def tendencia_ofertas(
    desde: date,
    hasta: date,
    carrera_id: str | None = None,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    parameters = _period(desde, hasta)
    query_id = "dashboard_tendencia_global"
    if carrera_id:
        parameters["carrera_id"] = _identifier(carrera_id, "carrera_id")
        query_id = "dashboard_tendencia_carrera"
    rows = await _execute(
        query_id, parameters, query_gateway=query_gateway, result_cache=result_cache
    )
    return {"periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()}, "filas": rows}


async def carreras_por_demanda(
    desde: date,
    hasta: date,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    rows = await _execute(
        "dashboard_carreras_demanda",
        {**_period(desde, hasta), "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"filas": rows}


async def demanda_dimension(
    tipo: str,
    carrera_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    slug = _dimension(tipo)
    career = await obtener_carrera(
        carrera_id, query_gateway=query_gateway, result_cache=result_cache
    )
    rows = await _execute(
        f"dashboard_demanda_{slug}",
        {**_period(desde, hasta), "carrera_id": career["id"], "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"tipo": slug, "carrera": career, "filas": rows}


async def cobertura_dimension(
    tipo: str,
    carrera_id: str,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    slug = _dimension(tipo)
    career = await obtener_carrera(
        carrera_id, query_gateway=query_gateway, result_cache=result_cache
    )
    if not career["cobertura_disponible"]:
        return {
            "tipo": slug,
            "carrera": career,
            "disponible": False,
            "motivo": "Curriculum coverage is not available for this career in the graph.",
            "filas": [],
        }
    rows = await _execute(
        f"dashboard_cobertura_{slug}",
        {"carrera_id": career["id"], "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"tipo": slug, "carrera": career, "disponible": True, "motivo": None, "filas": rows}


async def brechas_dimension(
    tipo: str,
    carrera_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    slug = _dimension(tipo)
    career = await obtener_carrera(
        carrera_id, query_gateway=query_gateway, result_cache=result_cache
    )
    if not career["cobertura_disponible"]:
        return {
            "tipo": slug,
            "carrera": career,
            "disponible": False,
            "motivo": "Breaches are unavailable because curriculum coverage is not connected.",
            "filas": [],
        }
    rows = await _execute(
        f"dashboard_brechas_{slug}",
        {**_period(desde, hasta), "carrera_id": career["id"], "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"tipo": slug, "carrera": career, "disponible": True, "motivo": None, "filas": rows}


async def industrias_por_carrera(
    carrera_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    career = await obtener_carrera(
        carrera_id, query_gateway=query_gateway, result_cache=result_cache
    )
    rows = await _execute(
        "dashboard_industrias_carrera_competencias",
        {**_period(desde, hasta), "carrera_id": career["id"], "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"carrera": career, "filas": rows}


async def industrias_elemento(
    tipo: str,
    elemento_id: str,
    desde: date,
    hasta: date,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    slug = _dimension(tipo)
    rows = await _execute(
        f"dashboard_industrias_{slug}",
        {**_period(desde, hasta), "elemento_id": elemento_id, "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"tipo": slug, "filas": rows}


async def empresas_dashboard(
    desde: date,
    hasta: date,
    limite: int = 10,
    *,
    query_gateway: TemplateQueryGateway | None = None,
    result_cache: QueryResultCache | None = None,
) -> dict[str, Any]:
    rows = await _execute(
        "dashboard_empresas",
        {**_period(desde, hasta), "limite": limite},
        query_gateway=query_gateway,
        result_cache=result_cache,
    )
    return {"filas": rows}


def validar_catalogo_dashboard() -> None:
    """Validate every active dashboard query without connecting to Neo4j."""
    examples: dict[str, Any] = {
        "carrera_id": "CAR_demo",
        "elemento_id": "COMP_demo",
        "desde": "2025-01-01",
        "hasta": "2025-02-01",
        "limite": 10,
    }
    for query in DASHBOARD_QUERIES.values():
        parameters = {name: examples[name] for name in query.required_parameters}
        guard_cypher(query.cypher, parameters)
