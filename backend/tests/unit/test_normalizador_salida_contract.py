"""Regression tests for the public curricular-output seam."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.modelos import ArchivoSilabo, ResultadoValidacionSilabos
from agente.normalizador.silabos.analista_llm import (
    ConceptoPropuesto,
    DecisionCurricular,
    _hash_id,
)
from agente.normalizador.silabos.salida import construir_salidas_curriculares


def _validacion() -> ResultadoValidacionSilabos:
    return ResultadoValidacionSilabos(
        archivo="curso.docx",
        carrera="MARKETING",
        periodo="2026-1",
        sha256="entrada",
        valida=True,
        archivos=(ArchivoSilabo("curso.docx", "docx", 1),),
        hallazgos=(),
    )


def _catalogo() -> CatalogoCHH:
    return CatalogoCHH(
        competencias=(
            ConceptoCHH("COMP_A", "Gestionar campañas", "Gestionar campañas."),
            ConceptoCHH("COMP_B", "Analizar mercados", "Analizar mercados."),
        ),
        habilidades=(
            ConceptoCHH("HAB_A", "Analizar campañas", "Analizar campañas."),
        ),
        herramientas=(
            ConceptoCHH("HERR_BEETRACK", "Beetrack", "Gestión logística."),
            ConceptoCHH("HERR_VTEX", "VTEX", "Comercio electrónico."),
        ),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def _registro() -> dict[str, object]:
    return {
        "id_silabo": "SIL_1",
        "id_curso": "CUR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "origen": {"archivo": "curso.docx", "formato": "docx"},
        "datos": {
            "curso": "Omnicanalidad",
            "coordinador": "Ana Pérez | Bruno Díaz",
            "creditos": "4",
            "nivel": "Séptimo",
            "tipo_curso": "Presencial",
            "codigo_curso": "MKT701",
            "logros_especificos": [
                {
                    "orden": "1",
                    "descripcion": "Analizar campañas",
                    "texto_evidencia": "Analizar campañas",
                }
            ],
            "competencias_declaradas": [
                {
                    "orden": "1",
                    "nombre": "Gestionar campañas",
                    "descripcion": "Gestionar campañas.",
                },
            ],
            "herramientas_evidencia": [
                {"seccion": "Recursos de aprendizaje", "texto": "Beetrack y VTEX."}
            ],
        },
    }


def test_course_csv_has_exact_schema_deduplicates_and_maps_execution_career(tmp_path: Path) -> None:
    registro = _registro()
    registro_duplicado = _registro()
    registro_duplicado["id_silabo"] = "SIL_2"
    construir_salidas_curriculares(
        [registro, registro_duplicado],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo(),
    )

    ruta_curso = tmp_path / "NOR_TEST" / "salidas" / "curso.csv"
    with ruta_curso.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        assert lector.fieldnames == [
            "id_curso", "nombre_curso", "coordinador", "creditos", "nivel",
            "tipo_curso", "codigo_curso", "id_carrera",
        ]
        filas = list(lector)
    assert filas == [
        {
            "id_curso": "CUR_1",
            "nombre_curso": "Omnicanalidad",
            "coordinador": "Ana Pérez | Bruno Díaz",
            "creditos": "4",
            "nivel": "Séptimo",
            "tipo_curso": "Presencial",
            "codigo_curso": "MKT701",
            "id_carrera": "CAR_9f09cddacdb2e0c1",
        }
    ]


def test_unknown_execution_career_blocks_without_inventing_car_id(tmp_path: Path) -> None:
    validacion = _validacion()
    validacion = ResultadoValidacionSilabos(
        archivo=validacion.archivo,
        carrera="CARRERA_NO_REGISTRADA",
        periodo=validacion.periodo,
        sha256=validacion.sha256,
        valida=validacion.valida,
        archivos=validacion.archivos,
        hallazgos=validacion.hallazgos,
    )
    resultado = construir_salidas_curriculares(
        [_registro()],
        validacion,
        tmp_path / "NOR_TEST",
        _catalogo(),
    )

    assert resultado.release_gate["decision"] == "BLOCK_IMPORT"
    assert any(
        hallazgo.codigo == "CARRERA_AUTORITATIVA_DESCONOCIDA"
        for hallazgo in resultado.hallazgos
    )


def _leer_jsonl(ruta: Path) -> list[dict[str, object]]:
    return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]


def _catalogo_sin_habilidad() -> CatalogoCHH:
    catalogo = _catalogo()
    return CatalogoCHH(
        competencias=catalogo.competencias,
        habilidades=(),
        herramientas=catalogo.herramientas,
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def test_public_seam_preserves_nn_lineage_for_each_source_mapping(tmp_path: Path) -> None:
    resultado = construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo(),
    )

    assert resultado.publicable is True
    reportes = tmp_path / "NOR_TEST" / "salidas" / "reportes"
    source_rows = _leer_jsonl(reportes / "cobertura_curricular_fuente.jsonl")
    canonical_rows = _leer_jsonl(reportes / "cobertura_curricular_canonica.jsonl")

    assert len(source_rows) == 2
    assert len(canonical_rows) == 2
    source_comp_tools = {
        (row["id_competencia_fuente"], row["id_herramienta_fuente"])
        for row in source_rows
    }
    source_competencies = {row["id_competencia_fuente"] for row in source_rows}
    source_tools = {row["id_herramienta_fuente"] for row in source_rows}
    assert len(source_competencies) == 1
    assert len(source_tools) == 2
    assert source_comp_tools == {
        (competencia, herramienta)
        for competencia in source_competencies
        for herramienta in source_tools
    }
    assert all(row["id_competencia"] == row["id_competencia_fuente"] for row in source_rows)
    assert all(row["id_habilidad"] == row["id_habilidad_fuente"] for row in source_rows)
    assert all(row["id_herramienta"] == row["id_herramienta_fuente"] for row in source_rows)
    required_lineage = {
        "id_ejecucion",
        "id_cob_curricular",
        "id_curso",
        "id_silabo",
        "id_logro",
        "id_competencia_fuente",
        "id_habilidad_fuente",
        "id_herramienta_fuente",
        "id_competencia_canonica",
        "id_habilidad_canonica",
        "id_herramienta_canonica",
        "source_ref",
    }
    assert all(required_lineage <= row.keys() for row in source_rows + canonical_rows)
    assert all(
        re.fullmatch(r"COB_CUR_[0-9a-f]{16}", row["id_cob_curricular"])
        for row in source_rows + canonical_rows
    )
    assert all(row["source_ref"] for row in source_rows + canonical_rows)
    assert {row["id_logro"] for row in canonical_rows} == {
        _hash_id("LOGRO_SRC", "SIL_1", "1", "Analizar campañas")
    }
    assert all(
        row["id_competencia"] == row["id_competencia_canonica"]
        and row["id_habilidad"] == row["id_habilidad_canonica"]
        and row["id_herramienta"] == row["id_herramienta_canonica"]
        for row in canonical_rows
    )
    canonical_comp_tools = {
        (row["id_competencia_canonica"], row["id_herramienta_canonica"])
        for row in canonical_rows
    }
    assert canonical_comp_tools == {
        (competencia, herramienta)
        for competencia in {row["id_competencia_canonica"] for row in canonical_rows}
        for herramienta in {row["id_herramienta_canonica"] for row in canonical_rows}
    }


def test_public_seam_keeps_source_tools_when_canonical_chain_is_pending(tmp_path: Path) -> None:
    construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo_sin_habilidad(),
    )

    reportes = tmp_path / "NOR_TEST" / "salidas" / "reportes"
    source_rows = _leer_jsonl(reportes / "cobertura_curricular_fuente.jsonl")
    canonical_rows = _leer_jsonl(reportes / "cobertura_curricular_canonica.jsonl")

    assert len(source_rows) == 2
    assert canonical_rows == []
    assert {row["id_herramienta_fuente"] for row in source_rows} == {
        row["id_herramienta"] for row in source_rows
    }
    assert {row["id_herramienta_canonica"] for row in source_rows} == {
        "HERR_BEETRACK",
        "HERR_VTEX",
    }
    assert all(row["id_habilidad_canonica"] == "" for row in source_rows)
    assert {row["source_ref"] for row in source_rows} == {"curso.docx"}


def test_pending_review_units_are_split_by_source_relation_identity(tmp_path: Path) -> None:
    construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo_sin_habilidad(),
    )

    reportes = tmp_path / "NOR_TEST" / "salidas" / "reportes"
    source_rows = _leer_jsonl(reportes / "cobertura_curricular_fuente.jsonl")
    pending_rows = _leer_jsonl(reportes / "pendientes_curriculares.jsonl")
    candidates = json.loads((reportes / "candidatos_curriculares.json").read_text(encoding="utf-8"))

    assert len(source_rows) == 2
    assert {row["id_cob_curricular"] for row in pending_rows} == {
        row["id_cob_curricular"] for row in source_rows
    }
    assert len({row["id_pendiente"] for row in pending_rows}) == 2
    assert {
        package["source_identity"]["id_cob_curricular"]
        for package in candidates["paquetes"]
    } == {row["id_cob_curricular"] for row in source_rows}
    assert all(len(package["source_relationships"]) == 1 for package in candidates["paquetes"])


def test_public_seam_preserves_revised_skill_proposal_without_accepting_it(
    tmp_path: Path,
) -> None:
    id_habilidad_fuente = _hash_id("HAB_SRC", "SIL_1", "1", "Analizar campañas")
    decision_revisada = DecisionCurricular(
        id_habilidad_fuente=id_habilidad_fuente,
        competencia=ConceptoPropuesto(nombre="Gestionar campañas"),
        habilidad=ConceptoPropuesto(
            nombre="Optimizar campañas omnicanal",
            descripcion="Optimizar campañas omnicanal con evidencia curricular.",
        ),
        evidencia=["Optimizar campañas omnicanal"],
        confianza=0.84,
    )

    construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo_sin_habilidad(),
        propuestas_llm={id_habilidad_fuente: decision_revisada},
    )

    reportes = tmp_path / "NOR_TEST" / "salidas" / "reportes"
    pendientes = _leer_jsonl(reportes / "pendientes_curriculares.jsonl")
    source_rows = _leer_jsonl(reportes / "cobertura_curricular_fuente.jsonl")
    canonical_rows = _leer_jsonl(reportes / "cobertura_curricular_canonica.jsonl")
    pendiente_habilidad = next(row for row in pendientes if row["tipo"] == "habilidad")

    assert pendiente_habilidad["propuesta"]["nombre"] == "Optimizar campañas omnicanal"
    assert pendiente_habilidad["propuesta"]["nombre"] != pendiente_habilidad[
        "descripcion_fuente"
    ]
    assert canonical_rows == []
    assert all(row["id_habilidad_canonica"] == "" for row in source_rows)
