"""Contrato HTTP de la publicación explícita y reversible."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from agente.api import neo4j_importacion, servidor


class FakeImportador:
    def previsualizar(self, id_ejecucion: str) -> dict[str, Any]:
        return {"id_ejecucion": id_ejecucion, "puede_importar": True}

    def importar(self, id_ejecucion: str, fingerprint: str, confirmar: bool) -> dict[str, Any]:
        return {
            "id_ejecucion": id_ejecucion,
            "fingerprint": fingerprint,
            "confirmar": confirmar,
            "estado": "completada",
        }

    def historial(self) -> list[dict[str, Any]]:
        return [{"id_importacion": "IMP_0123456789abcdef", "estado": "completada"}]

    def revertir(self, id_importacion: str, confirmar: bool) -> dict[str, Any]:
        return {"id_importacion": id_importacion, "confirmar": confirmar, "estado": "revertida"}


def test_publicacion_exige_confirmacion_y_expone_reversion(monkeypatch: Any) -> None:
    monkeypatch.setattr(neo4j_importacion, "importador_neo4j", FakeImportador())
    cliente = TestClient(servidor.app)

    validar = cliente.post(
        "/neo4j/validar",
        json={"id_ejecucion": "NOR_0123456789abcdef"},
    )
    assert validar.status_code == 200
    assert validar.json()["puede_importar"] is True

    sin_confirmar = cliente.post(
        "/neo4j/importar",
        json={
            "id_ejecucion": "NOR_0123456789abcdef",
            "fingerprint": "a" * 64,
            "confirmar": False,
        },
    )
    assert sin_confirmar.status_code == 200
    assert sin_confirmar.json()["confirmar"] is False

    historial = cliente.get("/neo4j/importaciones")
    assert historial.status_code == 200
    assert historial.json()["importaciones"][0]["estado"] == "completada"

    revertir = cliente.post(
        "/neo4j/importaciones/IMP_0123456789abcdef/revertir",
        json={"confirmar": True},
    )
    assert revertir.status_code == 200
    assert revertir.json()["estado"] == "revertida"
