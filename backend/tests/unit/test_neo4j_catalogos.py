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
    cobertura = filas["cobertura_curricular.csv"][0]
    assert cobertura["id_cobertura_curricular"] == cobertura["id_cob_curricular"]
    tx = TransaccionFalsa()

    neo4j_catalogos.escribir_catalogos(tx, filas, "IMP_1234567890abcdef")

    cypher = "\n".join(consulta for consulta, _ in tx.llamadas)
    coberturas_enviadas: list[dict[str, object]] = []
    for consulta, parametros in tx.llamadas:
        if "CoberturaCurricular" not in consulta:
            continue
        filas_enviadas = parametros["rows"]
        assert isinstance(filas_enviadas, list)
        assert all(isinstance(fila, dict) for fila in filas_enviadas)
        coberturas_enviadas.extend(filas_enviadas)
    assert coberturas_enviadas
    assert all(
        fila.get("id_cob_curricular") == fila.get("id_cobertura_curricular")
        for fila in coberturas_enviadas
    )
    assert "Silabo" in cypher
    assert "Logro" in cypher
    assert "ContenidoSemanal" not in cypher
    assert "Competencia" in cypher
    assert "Herramienta" not in cypher
    assert all(
        "MATCH (competencia" in consulta for consulta, _ in tx.llamadas if "EVIDENCIA" in consulta
    )
    assert all(
        fila["id_competencia"] for fila in filas["cobertura_curricular.csv"] if fila["id_logro"]
    )


@pytest.mark.parametrize("id_habilidad", ["HAB_TEC_007", "f9db583c7660"])
def test_materializa_habilidad_y_relaciones_de_cobertura_con_nombres_nuevos(
    id_habilidad: str,
) -> None:
    filas: dict[str, list[dict[str, str]]] = {
        nombre: [] for nombre, _ in neo4j_catalogos.ARCHIVOS_CATALOGO
    }
    filas["curso.csv"] = [
        {
            "id_curso": "CUR_1234567890abcdef",
            "nombre_curso": "Arquitectura",
            "coordinador": "",
            "creditos": "",
            "nivel": "",
            "tipo_curso": "Obligatorio",
            "naturaleza": "Taller",
            "codigo_curso": "A1",
            "id_carrera": "CAR_1234567890abcdef",
        }
    ]
    filas["silabo.csv"] = [
        {
            "id_silabo": "SIL_1234567890abcdef",
            "codigo_silabo": "A1",
            "sumilla": "",
            "id_curso": "CUR_1234567890abcdef",
            "periodo_academico": "2026-2",
        }
    ]
    filas["catalogo_habilidades.csv"] = [
        {
            "id_habilidad": id_habilidad,
            "id_carrera": "CAR_1234567890abcdef",
            "nombre_habilidad": "Diseño técnico",
            "desc_breve": "Diseña soluciones.",
        }
    ]
    filas["catalogo_logros.csv"] = [{"id_logro": "LOGRO_1234567890abcdef", "logro": "L1"}]
    filas["cobertura_curricular.csv"] = [
        {
            "id_cobertura_curricular": "COB_CUR_1234567890abcdef",
            "id_curso": "CUR_1234567890abcdef",
            "id_silabo": "SIL_1234567890abcdef",
            "id_competencia": "",
            "id_habilidad": id_habilidad,
            "id_logro": "LOGRO_1234567890abcdef",
        }
    ]

    tx = TransaccionFalsa()
    neo4j_catalogos.escribir_catalogos(tx, filas, "IMP_1234567890abcdef")
    consultas = "\n".join(consulta for consulta, _ in tx.llamadas)
    assert "MERGE (habilidad:Habilidad {id_habilidad: row.id_habilidad})" in consultas
    assert "habilidad.id_carrera = row.id_carrera" in consultas
    assert "CUBRE_HABILIDAD" in consultas
    assert "CUBRE_LOGRO" in consultas
    assert "TIENE_SILABO" not in consultas
    assert "CUBRE_COMPETENCIA" not in consultas
    assert "contexto.nombre_contextual = row.nombre_habilidad" in consultas
    assert "contexto.descripcion_contextual = row.desc_breve" in consultas
    assert "(carrera)-[" not in "\n".join(
        consulta for consulta, _ in tx.llamadas if "Habilidad" in consulta
    )


def test_habilidad_global_no_compara_id_carrera() -> None:
    filas: dict[str, list[dict[str, str]]] = {
        nombre: [] for nombre, _ in neo4j_catalogos.ARCHIVOS_CATALOGO
    }
    filas["catalogo_habilidades.csv"] = [
        {
            "id_habilidad": "HAB_TEC_007",
            "id_carrera": "CAR_1234567890abcdef",
            "nombre_habilidad": "Diseño técnico",
            "desc_breve": "Diseña soluciones.",
        }
    ]

    tx = TransaccionFalsa()
    neo4j_catalogos.escribir_catalogos(tx, filas, "IMP_1234567890abcdef")

    consulta, parametros = next(
        (consulta, parametros) for consulta, parametros in tx.llamadas if "Habilidad" in consulta
    )
    campos = parametros["campos"]
    assert isinstance(campos, list)
    assert campos == ["nombre_habilidad", "desc_breve"]
    assert "id_carrera" not in campos


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
