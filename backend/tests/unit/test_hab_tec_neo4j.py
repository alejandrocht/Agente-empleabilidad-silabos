"""Pruebas del publicador estructurado del catálogo HAB_TEC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from agente.normalizador.hab_tec_neo4j import ErrorPublicacionHabTec, PublicadorHabTecNeo4j


@dataclass
class _Habilidad:
    carrera: str
    id_hab_tec: str
    nombre: str
    descripcion: str
    fila: int = 1


class _Driver:
    def __init__(self) -> None:
        self.cerrado = False

    def close(self) -> None:
        self.cerrado = True


class _Sesion:
    def __init__(self, carreras: list[dict[str, str]]) -> None:
        self.carreras = carreras
        self.consultas: list[tuple[str, dict[str, Any]]] = []
        self.cerrada = False

    def run(self, cypher: str, **parametros: Any) -> list[dict[str, Any]]:
        self.consultas.append((cypher, parametros))
        if "MATCH (carrera:Carrera)" in cypher:
            return self.carreras
        return [{"habilidades": 1, "asociaciones": len(parametros["filas"])}]

    def close(self) -> None:
        self.cerrada = True


def test_publica_un_nodo_habilidad_y_contexto_en_relacion(monkeypatch: pytest.MonkeyPatch) -> None:
    publicador = PublicadorHabTecNeo4j()
    driver = _Driver()
    sesion = _Sesion(
        [{"id_carrera": "CAR_01", "nombre_carrera": "Ingeniería de Sistemas"}]
    )
    monkeypatch.setattr(publicador, "_sesion", lambda: (driver, sesion))

    resultado = publicador.publicar(
        [
            _Habilidad(
                "Ingeniería de Sistemas",
                "HAB_TEC_001",
                "Python",
                "Programación aplicada a datos",
            )
        ],
        "HABTEC_0123456789abcdef",
    )

    assert resultado == {"habilidades": 1, "asociaciones": 1}
    escritura, parametros = sesion.consultas[1]
    assert "MERGE (habilidad:Habilidad {id_habilidad: fila.id_habilidad})" in escritura
    assert "TIENE_HABILIDAD_TECNICA" in escritura
    assert parametros["filas"] == [
        {
            "id_habilidad": "HAB_TEC_001",
            "nombre_habilidad": "Python",
            "id_carrera": "CAR_01",
            "nombre_contextual": "Python",
            "descripcion_contextual": "Programación aplicada a datos",
            "id_catalogo": "HABTEC_0123456789abcdef",
        }
    ]
    assert driver.cerrado and sesion.cerrada


def test_no_escribe_si_alguna_carrera_del_catalogo_no_existe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publicador = PublicadorHabTecNeo4j()
    driver = _Driver()
    sesion = _Sesion([])
    monkeypatch.setattr(publicador, "_sesion", lambda: (driver, sesion))

    with pytest.raises(ErrorPublicacionHabTec, match="sin Carrera en Neo4j"):
        publicador.publicar(
            [_Habilidad("Carrera inexistente", "HAB_TEC_001", "Python", "Programación")],
            "HABTEC_0123456789abcdef",
        )

    assert len(sesion.consultas) == 1
    assert driver.cerrado and sesion.cerrada


def test_conserva_el_primer_nombre_como_canonico_por_id() -> None:
    filas = PublicadorHabTecNeo4j._resolver_asociaciones(
        [
            _Habilidad("Carrera A", "HAB_TEC_001", "Nombre canónico", "Contexto A", 2),
            _Habilidad("Carrera B", "HAB_TEC_001", "Nombre alternativo", "Contexto B", 3),
        ],
        {"carrera a": ["CAR_A"], "carrera b": ["CAR_B"]},
        "HABTEC_0123456789abcdef",
    )

    assert [fila["nombre_habilidad"] for fila in filas] == ["Nombre canónico", "Nombre canónico"]
    assert [fila["nombre_contextual"] for fila in filas] == [
        "Nombre canónico",
        "Nombre alternativo",
    ]
