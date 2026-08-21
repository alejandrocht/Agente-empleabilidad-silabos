from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from fastapi.testclient import TestClient

from agente.dashboard import servicio
from agente.utils.cypher_guard import guard_cypher
from api.servidor import app


class FakeGateway:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, parameters: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append((cypher, parameters))
        return self.rows


def test_every_active_dashboard_query_is_guarded_read_only() -> None:
    servicio.validar_catalogo_dashboard()


def test_dashboard_execution_uses_fixed_query_parameters_and_cache() -> None:
    gateway = FakeGateway([{"anio": 2025, "mes": 1, "ofertas": 3}])
    cache = servicio.QueryResultCache(ttl_seconds=60, max_entries=4)

    first = asyncio.run(
        servicio.tendencia_ofertas(
            date(2025, 1, 1),
            date(2025, 1, 31),
            query_gateway=gateway,
            result_cache=cache,
        )
    )
    second = asyncio.run(
        servicio.tendencia_ofertas(
            date(2025, 1, 1),
            date(2025, 1, 31),
            query_gateway=gateway,
            result_cache=cache,
        )
    )

    assert first == second == {
        "periodo": {"desde": "2025-01-01", "hasta": "2025-01-31"},
        "filas": [{"anio": 2025, "mes": 1, "ofertas": 3}],
    }
    assert len(gateway.calls) == 1
    query, parameters = gateway.calls[0]
    assert guard_cypher(query, parameters).limit == 100
    assert parameters == {"desde": "2025-01-01", "hasta": "2025-02-01"}


def test_dashboard_endpoint_rejects_unknown_dimension_without_database_call() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/dashboard/dimensiones/nope/demanda",
            params={
                "carrera_id": "CAR_demo",
                "desde": "2025-01-01",
                "hasta": "2025-01-31",
            },
        )

    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


def test_dashboard_endpoint_returns_stable_response_shape(monkeypatch) -> None:
    async def fake_metadata() -> dict[str, Any]:
        return {"periodo_disponible": {"desde": None, "hasta": None}, "dimensiones": []}

    monkeypatch.setattr("api.servidor.dashboard.metadatos", fake_metadata)

    with TestClient(app) as client:
        response = client.get("/dashboard/metadata")

    assert response.status_code == 200
    assert response.json() == {
        "periodo_disponible": {"desde": None, "hasta": None},
        "dimensiones": [],
    }


def test_dashboard_provider_failure_is_safe_and_non_leaking(monkeypatch) -> None:
    async def failing_metadata() -> dict[str, Any]:
        raise RuntimeError("private neo4j password and query text")

    monkeypatch.setattr("api.servidor.dashboard.metadatos", failing_metadata)

    with TestClient(app) as client:
        response = client.get("/dashboard/metadata")

    assert response.status_code == 503
    assert response.json() == {"detail": "Dashboard data is temporarily unavailable."}
    assert "private" not in response.text
