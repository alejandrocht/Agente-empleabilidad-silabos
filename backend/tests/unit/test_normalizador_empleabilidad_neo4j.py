"""Contrato de idempotencia del publicador laboral."""

from __future__ import annotations

from typing import Any

from agente.normalizador.empleabilidad.neo4j import ImportadorEmpleabilidadNeo4j


def _filas() -> dict[str, list[dict[str, str]]]:
    return {
        "empresa.csv": [{"id_empresa": "EMP_1", "nombre": "Empresa"}],
        "oferta_laboral.csv": [
            {"id_ofe_laboral": "LAB_1", "id_empresa": "EMP_1"},
            {"id_ofe_laboral": "LAB_2", "id_empresa": "EMP_1"},
            {"id_ofe_laboral": "LAB_3", "id_empresa": "EMP_1"},
        ],
        "puesto.csv": [],
        "catalogo_empleabilidad.csv": [],
        "habilidades_empleabilidad.csv": [],
        "herramientas_empleabilidad.csv": [],
        "requerimiento_laboral.csv": [],
    }


def test_consulta_duplicados_y_escribe_solo_ofertas_nuevas(monkeypatch: Any) -> None:
    importador = ImportadorEmpleabilidadNeo4j()
    escritas: list[list[dict[str, str]]] = []
    monkeypatch.setattr(importador, "_cargar", lambda _: (_filas(), "a" * 64))
    monkeypatch.setattr(importador, "_ofertas_existentes", lambda _: {"LAB_1"})
    monkeypatch.setattr(
        importador,
        "_escribir",
        lambda _filas, ofertas, _ids: escritas.append(ofertas),
    )

    preview = importador.previsualizar("NOR_0123456789abcdef")
    resultado = importador.importar("NOR_0123456789abcdef", "a" * 64, confirmar=True)

    assert preview["resumen"] == {
        "publicaciones_nuevas": 2,
        "publicaciones_existentes": 1,
        "consultas_ejecutadas": 1,
    }
    assert resultado["resumen"]["publicaciones_creadas"] == 2
    assert [fila["id_ofe_laboral"] for fila in escritas[0]] == ["LAB_2", "LAB_3"]
