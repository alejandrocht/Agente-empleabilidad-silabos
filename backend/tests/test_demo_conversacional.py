from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from agente.demo_conversacional import PREGUNTAS_DEMO, responder_demo
from api import servidor


class GatewayDemo:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.cypher = ""

    async def run(
        self,
        cypher: str,
        parameters: object,
        *,
        allow_unbounded: bool = False,
    ) -> list[dict[str, object]]:
        self.cypher = cypher
        self.parameters = parameters
        assert allow_unbounded is True
        return self.rows


def test_demo_catalog_has_five_guarded_read_queries() -> None:
    assert len(PREGUNTAS_DEMO) == 5
    for item in PREGUNTAS_DEMO:
        assert "LIMIT" not in item.cypher.upper()
    assert all("$habilidades_oficiales" in item.cypher for item in PREGUNTAS_DEMO[:4])
    assert "$catalogo_oficial" in PREGUNTAS_DEMO[4].cypher


def test_demo_response_uses_gateway_rows_without_an_llm() -> None:
    gateway = GatewayDemo(
        [{"habilidad": "Preparar informes operativos.", "cursos": 1, "ofertas": 7}]
    )

    result = asyncio.run(
        responder_demo(
            "¿Qué habilidades enseñadas en Ingeniería Industrial también solicitan "
            "las ofertas dirigidas a esa carrera?",
            query_gateway=gateway,
        )
        )

    assert "Preparar informes operativos." in result["respuesta"]
    assert "ofertas: 7" in result["respuesta"]
    assert "MATCH (ca:Carrera)" in gateway.cypher
    assert "CUBRE" in gateway.cypher
    assert "$habilidades_oficiales" in gateway.cypher
    assert isinstance(gateway.parameters, dict)
    assert len(gateway.parameters["habilidades_oficiales"]) == 21
    assert result["modo"] == "demo"


def test_demo_response_preserves_all_gateway_rows_without_a_limit() -> None:
    rows = [
        {"carrera": "Ingeniería Industrial", "habilidades_compartidas": index}
        for index in range(11)
    ]
    gateway = GatewayDemo(rows)

    result = asyncio.run(
        responder_demo(
            "¿Qué carreras tienen más habilidades compartidas entre su currícula "
            "y el mercado laboral?",
            query_gateway=gateway,
        )
    )

    assert result["filas"] == rows
    assert isinstance(gateway.parameters, dict)
    assert len(gateway.parameters["catalogo_oficial"]) == 277


def test_demo_stream_returns_langgraph_compatible_values(monkeypatch) -> None:
    async def fake_demo(_pregunta: str) -> dict[str, str]:
        return {
            "respuesta": "Respuesta demo",
            "cypher": "MATCH (n:Carrera) RETURN count(n) AS total LIMIT 1",
        }

    monkeypatch.setenv("CIAR_DEMO_MODE", "1")
    monkeypatch.setattr(servidor, "responder_demo", fake_demo)

    with TestClient(servidor.app) as client:
        response = client.post(
            "/chat/stream",
            json={
                "input": {
                    "pregunta": (
                        "¿Qué habilidades enseñadas en Ingeniería Industrial también "
                        "solicitan las ofertas dirigidas a esa carrera?"
                    )
                }
            },
        )

    assert response.status_code == 200
    assert "event: values" in response.text
    values_line = next(
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: {") and '"respuesta"' in line
    )
    assert json.loads(values_line)["modo"] == "demo"
    assert "event: messages" in response.text
