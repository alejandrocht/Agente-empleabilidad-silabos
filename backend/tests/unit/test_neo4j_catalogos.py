from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest

neo4j_catalogos: Any = importlib.import_module("agente.db.neo4j_catalogos")
salida_catalogos: Any = importlib.import_module("agente.normalizador.silabos.salida_catalogos")


class TransaccionFalsa:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, dict[str, object]]] = []

    def run(self, cypher: str, parametros: dict[str, object]) -> list[dict[str, int]]:
        self.llamadas.append((cypher, parametros))
        filas = parametros["rows"]
        assert isinstance(filas, list)
        return [{"total": len(filas)}]


def _crear_catalogos(ruta: Path) -> None:
    salida_catalogos.construir_catalogos_curriculares(
        [
            {
                "id_curso": "CUR_1234567890abcdef",
                "id_silabo": "SIL_1234567890abcdef",
                "carrera": "SISTEMAS",
                "periodo": "2026-2",
                "datos": {
                    "nombre_curso": "Arquitectura de software",
                    "codigo_curso": "650062",
                    "sumilla": "Diseño de sistemas.",
                    "competencias_declaradas": [
                        {
                            "nombre": "Pensamiento sistémico",
                            "descripcion": "Analiza sistemas.",
                            "codigo": "G1",
                            "tipo": "generica",
                        }
                    ],
                    "logro_general": "Diseña una arquitectura mantenible.",
                    "logros_especificos": [
                        {
                            "descripcion": "Compara estilos arquitectónicos.",
                            "codigos_competencia": ["G1"],
                        }
                    ],
                    "programa_analitico_detalle": [
                        {
                            "semana": "1",
                            "tema": "Fundamentos",
                            "contenido": "Atributos de calidad.",
                        }
                    ],
                },
            }
        ],
        ruta,
        carrera="SISTEMAS",
        periodo_academico="2026-2",
    )


def test_importer_maps_public_description_to_existing_graph_property() -> None:
    filas: dict[str, list[dict[str, str]]] = {
        nombre: [] for nombre, _ in neo4j_catalogos.ARCHIVOS_CATALOGO
    }
    filas["catalogo_competencias.csv"] = [
        {
            "id_competencia": "COMP_1234567890abcdef",
            "nombre_competencia": "Pensamiento sistémico",
            "descripcion_breve": "Analiza sistemas.",
            "tipo_competencia": "generica",
            "codigo_competencia": "G1",
        }
    ]

    tx = TransaccionFalsa()
    neo4j_catalogos.escribir_catalogos(tx, filas, "IMP_1234567890abcdef")

    consulta, parametros = next(
        (consulta, parametros) for consulta, parametros in tx.llamadas if "Competencia" in consulta
    )
    filas_enviadas = parametros["rows"]
    assert isinstance(filas_enviadas, list)
    assert filas_enviadas[0]["descripcion_breve_competencia"] == "Analiza sistemas."
    assert "descripcion_breve" not in filas_enviadas[0]
    campos = parametros["campos"]
    assert isinstance(campos, list)
    assert "descripcion_breve_competencia" in campos
    assert "existente[campo] <> row[campo]" in consulta
    assert (
        "competencia.descripcion_breve_competencia = row.descripcion_breve_competencia" in consulta
    )


def test_importa_nuevo_contrato_sin_habilidades_ni_herramientas(tmp_path: Path) -> None:
    _crear_catalogos(tmp_path)
    filas = neo4j_catalogos.leer_catalogos(tmp_path)
    competencia = filas["catalogo_competencias.csv"][0]
    assert competencia["descripcion_breve"] == "Analiza sistemas."
    assert "descripcion_breve_competencia" not in competencia
    tx = TransaccionFalsa()

    neo4j_catalogos.escribir_catalogos(tx, filas, "IMP_1234567890abcdef")

    cypher = "\n".join(consulta for consulta, _ in tx.llamadas)
    assert "Silabo" in cypher
    assert "Logro" in cypher
    assert "ContenidoSemanal" not in cypher
    assert "Competencia" in cypher
    assert "Habilidad" not in cypher
    assert "Herramienta" not in cypher
    assert all(
        "MATCH (competencia" in consulta for consulta, _ in tx.llamadas if "EVIDENCIA" in consulta
    )
    assert all(
        fila["id_competencia"] for fila in filas["cobertura_curricular.csv"] if fila["id_logro"]
    )


def test_rechaza_logro_sin_competencia(tmp_path: Path) -> None:
    _crear_catalogos(tmp_path)
    filas = neo4j_catalogos.leer_catalogos(tmp_path)
    fila_logro = next(fila for fila in filas["cobertura_curricular.csv"] if fila["id_logro"])
    fila_logro["id_competencia"] = ""

    with pytest.raises(ValueError, match="Todo logro debe relacionarse"):
        neo4j_catalogos.escribir_catalogos(TransaccionFalsa(), filas, "IMP_1234567890abcdef")


def test_rechaza_cobertura_con_referencia_inexistente(tmp_path: Path) -> None:
    _crear_catalogos(tmp_path)
    cobertura = tmp_path / "cobertura_curricular.csv"
    contenido = cobertura.read_text(encoding="utf-8-sig")
    cobertura.write_text(
        contenido.replace("COMP_", "COMP_ffffffffffffffff#", 1),
        encoding="utf-8-sig",
    )

    with pytest.raises(ValueError, match="id_competencia inválido"):
        neo4j_catalogos.leer_catalogos(tmp_path)
