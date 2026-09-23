from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

_salida_catalogos = importlib.import_module("agente.normalizador.silabos.salida_catalogos")
ARCHIVOS_CATALOGO: tuple[tuple[str, tuple[str, ...]], ...] = _salida_catalogos.ARCHIVOS_CATALOGO
construir_catalogos_curriculares: Any = _salida_catalogos.construir_catalogos_curriculares
construir_salidas_tecnicas: Any = _salida_catalogos.construir_salidas_tecnicas


def _registro() -> dict[str, object]:
    return {
        "id_curso": "CUR_1234567890abcdef",
        "id_silabo": "SIL_1234567890abcdef",
        "carrera": "SISTEMAS",
        "periodo": "2026-2",
        "datos": {
            "nombre_curso": "Arquitectura de software",
            "coordinador": "Ada Lovelace",
            "creditos": "4",
            "nivel": "Séptimo",
            "tipo_curso": "Obligatorio",
            "naturaleza": "Taller",
            "codigo_curso": "650062",
            "sumilla": "Diseño de sistemas de software.",
            "competencias_declaradas": [
                {
                    "nombre": "Pensamiento sistémico",
                    "descripcion": "Analiza sistemas como un conjunto.",
                    "codigo": "G1",
                    "tipo": "generica",
                },
                {
                    "nombre": "Diseño de ingeniería",
                    "descripcion": "Diseña soluciones de ingeniería.",
                    "codigo": "E1",
                    "tipo": "especifica",
                },
            ],
            "logro_general": "Diseña una arquitectura de software mantenible.",
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
                    "contenido": "Atributos de calidad y decisiones arquitectónicas.",
                }
            ],
        },
    }


def _leer_csv(ruta: Path) -> list[dict[str, str]]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def test_catalogo_competencias_emite_header_publico_y_conserva_descripcion(
    tmp_path: Path,
) -> None:
    construir_catalogos_curriculares(
        [_registro()],
        tmp_path,
        carrera="SISTEMAS",
        periodo_academico="2026-2",
    )

    ruta = tmp_path / "catalogo_competencias.csv"
    lineas = ruta.read_text(encoding="utf-8-sig").splitlines()
    assert lineas[0] == (
        "id_competencia,nombre_competencia,descripcion_breve,tipo_competencia,codigo_competencia"
    )
    filas = list(csv.DictReader(lineas))

    assert filas
    assert all(fila["descripcion_breve"] for fila in filas)
    assert all("descripcion_breve_competencia" not in fila for fila in filas)


def test_materializa_contrato_curricular_sin_herramientas(tmp_path: Path) -> None:
    registro = _registro()
    tecnica = {
        "id_silabo": registro["id_silabo"],
        "estado_aprobacion": "APROBADA",
        "catalogo_ref": "COMP_TEC_0007",
        "nombre_competencia": "Diseño técnico de arquitecturas",
        "descripcion_breve_competencia": (
            "Selecciona estructuras y patrones según atributos de calidad."
        ),
        "logros": ["Compara estilos arquitectónicos."],
        "evidencia": [
            {
                "fuente": "semana",
                "numero_semana": "1",
                "fragmento": "Atributos de calidad y decisiones arquitectónicas.",
            }
        ],
        "justificacion": "La semana exige decisiones técnicas de arquitectura.",
        "confianza": 0.91,
    }

    resumen = construir_catalogos_curriculares(
        [registro],
        tmp_path,
        carrera="SISTEMAS",
        periodo_academico="2026-2",
        competencias_tecnicas=[tecnica],
    )

    assert {ruta.name for ruta in tmp_path.glob("*.csv")} == {
        nombre for nombre, _ in ARCHIVOS_CATALOGO
    }
    assert not (tmp_path / "catalogo_herramientas.csv").exists()
    assert resumen["inferencias_tecnicas"] == 1

    silabos = _leer_csv(tmp_path / "silabo.csv")
    assert silabos == [
        {
            "id_silabo": "SIL_1234567890abcdef",
            "codigo_silabo": "650062",
            "sumilla": "Diseño de sistemas de software.",
            "id_curso": "CUR_1234567890abcdef",
            "periodo_academico": "2026-2",
        }
    ]
    competencias = _leer_csv(tmp_path / "catalogo_competencias.csv")
    assert {fila["tipo_competencia"] for fila in competencias} == {
        "generica",
        "especifica",
    }
    habilidades = _leer_csv(tmp_path / "catalogo_habilidades.csv")
    assert habilidades == [
        {
            "id_habilidad": "HAB_TEC_0007",
            "id_carrera": "CAR_3658c834b24e31a0",
            "nombre_habilidad": "Diseño técnico de arquitecturas",
            "desc_breve": "Selecciona estructuras y patrones según atributos de calidad.",
        }
    ]
    tecnica_csv = habilidades[0]

    logros = _leer_csv(tmp_path / "catalogo_logros.csv")
    assert {fila["logro"] for fila in logros} == {
        "Diseña una arquitectura de software mantenible.",
        "Compara estilos arquitectónicos.",
    }
    cobertura = _leer_csv(tmp_path / "cobertura_curricular.csv")
    logro_general = next(
        fila
        for fila in logros
        if fila["logro"] == "Diseña una arquitectura de software mantenible."
    )
    relaciones_generales = [
        fila for fila in cobertura if fila["id_logro"] == logro_general["id_logro"]
    ]
    competencias_declaradas = {
        fila["id_competencia"] for fila in competencias if fila["tipo_competencia"] != "tecnica"
    }
    assert {fila["id_competencia"] for fila in relaciones_generales} == (competencias_declaradas)
    assert all(
        fila["id_competencia"] or fila["id_habilidad"] for fila in cobertura if fila["id_logro"]
    )
    assert any(
        fila["id_habilidad"] == tecnica_csv["id_habilidad"]
        and not fila["id_competencia"]
        and fila["id_logro"]
        for fila in cobertura
    )

    assert not (tmp_path / "contenido_semanal.csv").exists()
    inferencia = json.loads(
        (tmp_path / "inferencias_tecnicas.jsonl").read_text(encoding="utf-8").strip()
    )
    assert inferencia["id_habilidad"] == tecnica_csv["id_habilidad"]
    assert inferencia["evidencia"][0]["numero_semana"] == "1"


def test_rechaza_tecnica_aprobada_sin_catalogo_ref_seguro(tmp_path: Path) -> None:
    tecnica = {
        "id_silabo": "SIL_1234567890abcdef",
        "estado_aprobacion": "APROBADA",
        "nombre_competencia": "Diseño técnico de arquitecturas",
        "descripcion_breve_competencia": "Selecciona estructuras técnicas.",
        "logros": ["Diseña una arquitectura de software mantenible."],
    }

    with pytest.raises(ValueError, match="catalogo_ref.*COMP_TEC_####"):
        construir_catalogos_curriculares(
            [_registro()],
            tmp_path,
            carrera="SISTEMAS",
            periodo_academico="2026-2",
            competencias_tecnicas=[tecnica],
        )


def test_materializa_tecnica_aprobada_sin_competencia_declarada(
    tmp_path: Path,
) -> None:
    registro = _registro()
    datos = registro["datos"]
    assert isinstance(datos, dict)
    datos["competencias_declaradas"] = []
    datos["logros_especificos"] = []
    tecnica = {
        "id_silabo": registro["id_silabo"],
        "estado_aprobacion": "APROBADA",
        "catalogo_ref": "COMP_TEC_0007",
        "nombre_competencia": "Diseño técnico de arquitecturas",
        "descripcion_breve_competencia": (
            "Selecciona estructuras y patrones según atributos de calidad."
        ),
        "logros": [datos["logro_general"]],
    }

    resultado = construir_salidas_tecnicas(
        [registro],
        tmp_path,
        carrera="SISTEMAS",
        periodo_academico="2026-2",
        propuestas_aprobadas=[tecnica],
        analisis_tecnico={"estado": "COMPLETADO"},
    )

    assert resultado.publicable is True
    assert resultado.cuarentena == ()
    assert resultado.release_gate["decision"] == "ALLOW_IMPORT"
    competencias = _leer_csv(tmp_path / "catalogo_competencias.csv")
    assert not [fila for fila in competencias if fila["tipo_competencia"] == "tecnica"]
    habilidades = _leer_csv(tmp_path / "catalogo_habilidades.csv")
    assert habilidades[0]["id_habilidad"] == "HAB_TEC_0007"
    cobertura = _leer_csv(tmp_path / "cobertura_curricular.csv")
    assert len(cobertura) == 1
    assert cobertura[0]["id_habilidad"] == "HAB_TEC_0007"


def test_rechaza_lotes_que_mezclan_carreras_o_periodos(tmp_path: Path) -> None:
    registro = _registro()
    registro["carrera"] = "INDUSTRIAL"

    with pytest.raises(ValueError, match="mezcla carreras"):
        construir_catalogos_curriculares(
            [registro], tmp_path, carrera="SISTEMAS", periodo_academico="2026-2"
        )


def test_codigos_c_institucionales_se_clasifican_como_genericos() -> None:
    from agente.normalizador.silabos.extraccion_curricular import (
        _codigos,
        _tipo_competencia_codigo,
    )

    assert _codigos("C7") == ["C7"]
    assert _tipo_competencia_codigo("C7") == "generica"


def test_ids_de_silabo_cambian_con_periodo_y_curso_permanece_estable() -> None:
    from agente.normalizador.silabos.extraccion_curricular import _ids_curriculares

    silabo_1, curso_1 = _ids_curriculares("SISTEMAS", "2026-1", "Curso", "650062")
    silabo_2, curso_2 = _ids_curriculares("SISTEMAS", "2026-2", "Curso", "650062")

    assert silabo_1 != silabo_2
    assert curso_1 == curso_2


def test_no_materializa_propuesta_tecnica_pendiente(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="pendiente de aprobación"):
        construir_catalogos_curriculares(
            [_registro()],
            tmp_path,
            carrera="SISTEMAS",
            periodo_academico="2026-2",
            competencias_tecnicas=[
                {
                    "id_silabo": "SIL_1234567890abcdef",
                    "nombre_competencia": "Diseño técnico de arquitecturas",
                    "descripcion_breve_competencia": "Selecciona estructuras técnicas.",
                    "estado_aprobacion": "PENDIENTE_APROBACION",
                }
            ],
        )


def test_rechaza_propuesta_tecnica_sin_aprobacion_exacta(tmp_path: Path) -> None:
    for estado in (None, "", " aprobada", "aprobada"):
        tecnica = {
            "id_silabo": "SIL_1234567890abcdef",
            "nombre_competencia": "Diseño técnico de arquitecturas",
            "descripcion_breve_competencia": "Selecciona estructuras técnicas.",
            "estado_aprobacion": estado,
        }
        with pytest.raises(ValueError, match="pendiente de aprobación"):
            construir_catalogos_curriculares(
                [_registro()],
                tmp_path,
                carrera="SISTEMAS",
                periodo_academico="2026-2",
                competencias_tecnicas=[tecnica],
            )


def test_materializacion_rechaza_relacion_tecnica_sin_logro_valido(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="logro inexistente"):
        construir_catalogos_curriculares(
            [_registro()],
            tmp_path,
            carrera="SISTEMAS",
            periodo_academico="2026-2",
            competencias_tecnicas=[
                {
                    "id_silabo": "SIL_1234567890abcdef",
                    "nombre_competencia": "Diseño técnico de arquitecturas",
                    "descripcion_breve_competencia": "Selecciona estructuras técnicas.",
                    "estado_aprobacion": "APROBADA",
                    "catalogo_ref": "COMP_TEC_0007",
                    "logros": ["Este logro no existe en el sílabo."],
                }
            ],
        )


def test_unlinked_source_outcome_keeps_csv_and_quarantines_only_its_relation(
    tmp_path: Path,
) -> None:
    registro = _registro()
    datos = registro["datos"]
    assert isinstance(datos, dict)
    logros_especificos = datos["logros_especificos"]
    assert isinstance(logros_especificos, list)
    logros_especificos[0] = {
        "descripcion": "Compara estilos arquitectónicos.",
        "codigos_competencia": ["NO_EXISTE"],
    }

    resultado = construir_salidas_tecnicas(
        [registro],
        tmp_path,
        carrera="SISTEMAS",
        periodo_academico="2026-2",
        analisis_tecnico={"estado": "COMPLETADO"},
    )

    assert {ruta.name for ruta in tmp_path.glob("*.csv")} == {
        nombre for nombre, _ in ARCHIVOS_CATALOGO
    }
    logros = _leer_csv(tmp_path / "catalogo_logros.csv")
    outcome = next(fila for fila in logros if fila["logro"] == "Compara estilos arquitectónicos.")
    cobertura = _leer_csv(tmp_path / "cobertura_curricular.csv")
    assert all(fila["id_logro"] != outcome["id_logro"] for fila in cobertura)
    assert resultado.cuarentena[0]["codigo"] == "LOGRO_SIN_COMPETENCIA"
    assert resultado.cuarentena[0]["logro"] == "Compara estilos arquitectónicos."
    assert resultado.release_gate["decision"] == "BLOCK_IMPORT"
    assert "UNLINKED_SOURCE_OUTCOME" in resultado.release_gate["blockers"]
    assert any(hallazgo.codigo == "LOGRO_SIN_COMPETENCIA" for hallazgo in resultado.hallazgos)
