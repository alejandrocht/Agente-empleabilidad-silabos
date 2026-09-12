"""Regression tests for the public curricular-output seam."""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import re
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.identidad import hashed
from agente.normalizador.modelos import ArchivoSilabo, Hallazgo, ResultadoValidacionSilabos
from agente.normalizador.silabos import (
    normalizacion_curricular,
    release_gate,
    resolucion_curricular,
    salida,
    trazabilidad_curricular,
    validacion_salida,
)
from agente.normalizador.silabos.analista_llm import (
    ConceptoPropuesto,
    DecisionCurricular,
    _hash_id,
)
from agente.normalizador.silabos.salida import construir_salidas_curriculares
from agente.normalizador.silabos.trazabilidad_curricular import _id_logro


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
            ConceptoCHH("COMP_A", "Gestionar campañas", "Gestionar campañas.", "tecnica"),
            ConceptoCHH("COMP_B", "Analizar mercados", "Analizar mercados.", "tecnica"),
        ),
        habilidades=(ConceptoCHH("HAB_A", "Analizar campañas", "Analizar campañas."),),
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
            "nivel": "7",
            "tipo_curso": "Obligatorio",
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
            "id_curso",
            "nombre_curso",
            "coordinador",
            "creditos",
            "nivel",
            "tipo_curso",
            "codigo_curso",
            "id_carrera",
        ]
        filas = list(lector)
    assert filas == [
        {
            "id_curso": "CUR_1",
            "nombre_curso": "Omnicanalidad",
            "coordinador": "Ana Pérez | Bruno Díaz",
            "creditos": "4",
            "nivel": "7",
            "tipo_curso": "Obligatorio",
            "codigo_curso": "MKT701",
            "id_carrera": "CAR_9f09cddacdb2e0c1",
        }
    ]


COMPETENCIAS_FIELD_NAMES = [
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
    "codigo_competencia",
]


def _competencias_rows(tmp_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    ruta = tmp_path / "NOR_TEST" / "salidas" / "catalogo_competencias.csv"
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        return list(lector.fieldnames or []), list(lector)


def _registro_con_declaraciones(
    declaraciones: list[dict[str, str]],
    id_silabo: str = "SIL_1",
) -> dict[str, object]:
    """Construye un registro cuyo sílabo declara las competencias indicadas."""

    registro = _registro()
    registro["id_silabo"] = id_silabo
    registro["id_curso"] = f"CUR_{id_silabo}"
    datos = registro["datos"]
    assert isinstance(datos, dict)
    datos["competencias_declaradas"] = declaraciones
    return registro


def test_competency_catalog_emits_declared_curriculum_codes(tmp_path: Path) -> None:
    """Las competencias genéricas y específicas declaradas publican su código."""

    registro = _registro_con_declaraciones(
        [
            {
                "orden": "1",
                "nombre": "Gestionar campañas",
                "descripcion": "Gestionar campañas.",
                "codigo": "G7",
            },
            {
                "orden": "2",
                "nombre": "Analizar mercados",
                "descripcion": "Analizar mercados.",
                "codigo": "E2",
            },
        ]
    )

    resultado = construir_salidas_curriculares(
        [registro], _validacion(), tmp_path / "NOR_TEST", _catalogo()
    )

    assert resultado.publicable is True
    encabezado, filas = _competencias_rows(tmp_path)
    assert encabezado == COMPETENCIAS_FIELD_NAMES
    assert {fila["nombre_competencia"]: fila["codigo_competencia"] for fila in filas} == {
        "Gestionar campañas": "G7",
        "Analizar mercados": "E2",
    }


def test_competency_catalog_leaves_code_empty_when_syllabus_declares_none(
    tmp_path: Path,
) -> None:
    """Una competencia técnica inferida por el modelo no declara código curricular."""

    registro = _registro_con_declaraciones(
        [
            {
                "orden": "1",
                "nombre": "Gestionar campañas",
                "descripcion": "Gestionar campañas.",
            }
        ]
    )

    resultado = construir_salidas_curriculares(
        [registro], _validacion(), tmp_path / "NOR_TEST", _catalogo()
    )

    assert resultado.publicable is True
    encabezado, filas = _competencias_rows(tmp_path)
    assert encabezado == COMPETENCIAS_FIELD_NAMES
    assert [fila["codigo_competencia"] for fila in filas] == [""]


def test_competency_catalog_keeps_first_non_empty_code_per_canonical_competency(
    tmp_path: Path,
) -> None:
    """Varias declaraciones de la misma competencia canónica no pisan el primer código."""

    sin_codigo = {
        "orden": "1",
        "nombre": "Gestionar campañas",
        "descripcion": "Gestionar campañas.",
    }
    registros = [
        _registro_con_declaraciones([sin_codigo], id_silabo="SIL_1"),
        _registro_con_declaraciones([{**sin_codigo, "codigo": "G7"}], id_silabo="SIL_2"),
        _registro_con_declaraciones([{**sin_codigo, "codigo": "E2"}], id_silabo="SIL_3"),
    ]

    resultado = construir_salidas_curriculares(
        registros, _validacion(), tmp_path / "NOR_TEST", _catalogo()
    )

    assert resultado.publicable is True
    _, filas = _competencias_rows(tmp_path)
    assert [fila["codigo_competencia"] for fila in filas] == ["G7"]


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
        hallazgo.codigo == "CARRERA_AUTORITATIVA_DESCONOCIDA" for hallazgo in resultado.hallazgos
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
        (row["id_competencia_fuente"], row["id_herramienta_fuente"]) for row in source_rows
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
    assert all(row["id_logro"] == row["id_logro_fuente"] for row in source_rows)
    assert all(row["id_herramienta"] == row["id_herramienta_fuente"] for row in source_rows)
    required_lineage = {
        "id_ejecucion",
        "id_cob_curricular",
        "id_curso",
        "id_silabo",
        "id_logro",
        "id_logro_fuente",
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
    # El logro publicado se identifica por su nombre; su origen por sílabo y
    # orden queda en la columna de provenance `id_logro_fuente`.
    assert {row["id_logro"] for row in canonical_rows} == {_id_logro("Analizar campañas")}
    assert {row["id_logro_fuente"] for row in canonical_rows} == {
        _hash_id("LOGRO_SRC", "SIL_1", "1", "Analizar campañas")
    }
    assert all(
        row["id_competencia"] == row["id_competencia_canonica"]
        and row["id_logro"] == row["id_habilidad_canonica"]
        and row["id_herramienta"] == row["id_herramienta_canonica"]
        for row in canonical_rows
    )
    canonical_comp_tools = {
        (row["id_competencia_canonica"], row["id_herramienta_canonica"]) for row in canonical_rows
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
        package["source_identity"]["id_cob_curricular"] for package in candidates["paquetes"]
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
    assert pendiente_habilidad["propuesta"]["nombre"] != pendiente_habilidad["descripcion_fuente"]
    assert canonical_rows == []
    assert all(row["id_habilidad_canonica"] == "" for row in source_rows)


def _hashes_de_artefactos(salida: Path) -> dict[str, str]:
    return {
        ruta.relative_to(salida).as_posix(): hashlib.sha256(ruta.read_bytes()).hexdigest()
        for ruta in sorted(salida.rglob("*"))
        if ruta.is_file()
    }


def test_validation_extraction_preserves_contracts_and_facade(tmp_path: Path) -> None:
    canonico = construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "canonical" / "NOR_TEST",
        _catalogo(),
    )
    pendiente = construir_salidas_curriculares(
        [_registro()],
        _validacion(),
        tmp_path / "pending" / "NOR_TEST",
        _catalogo_sin_habilidad(),
    )

    assert _hashes_de_artefactos(tmp_path / "canonical" / "NOR_TEST" / "salidas") == {
        "catalogo_competencias.csv": (
            "dab33b8ba44f4dce85d2f432fae1e40caf98b350ba522b576bfaf9014d76bc40"
        ),
        "catalogo_herramientas.csv": (
            "b7e8db9bb823a80d174720b9b5c606d03bb71a35fe281835c306956cf67e405a"
        ),
        "catalogo_logros.csv": ("7b6c33e9ff3e411a3ddb88668580ff5ac2a0154f07662bae56dd137fdf99e115"),
        "cobertura_curricular.csv": (
            "b6cd6e53a27d1a8b7763e04c59ae22c5aaf3e013dc5157dd12547ee747393e45"
        ),
        "curso.csv": ("02bbc9fd7fc3236eec084aa6241dd1094c4b18d510c5e707201e706bbc326498"),
        "reportes/candidatos_curriculares.json": (
            "32acfe11bd659061af0e35b0479c143490ec64e17070e5b5222257e94daa411d"
        ),
        "reportes/cobertura_curricular_canonica.jsonl": (
            "4150334bceb43052e202532e66fdd12e57794575003b225b353df3f444f412ba"
        ),
        "reportes/cobertura_curricular_fuente.jsonl": (
            "8d5d7e2a8098edd1a758aa81c4b8f135e4ae02c1ad6b7259b667fe8aa1e02050"
        ),
        "reportes/competencias_fuente.jsonl": (
            "5d6896b52cbe40efb9303ae6ee9fd1df0afc1b63d9dedeb21c58c686c64d553d"
        ),
        "reportes/habilidades_fuente.jsonl": (
            "1d091e44605d8e289203436d14dd76c153abfeec95d5451596882ef5ddd357f1"
        ),
        "reportes/herramientas_fuente.jsonl": (
            "b694b01617ea61ea2e3e49fd44ca6ea14763666a5f2097530a2e49b5a60cbb85"
        ),
        "reportes/pendientes_curriculares.jsonl": (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        "reportes/release_gate.json": (
            "8614efde2b6c89ec92823aefe9b87bf86d6a81aaca62243fe8bf80dfb1d954d2"
        ),
        "silabo.csv": ("86db76a18db9aa91216c28c4758e36d48427fc2263794c291adb4c609429db64"),
    }
    assert _hashes_de_artefactos(tmp_path / "pending" / "NOR_TEST" / "salidas") == {
        "reportes/candidatos_curriculares.json": (
            "e6594f177e49a85d164a56e269a22e9bfc5af38b8702a0ad2295f2f9997c6bd6"
        ),
        "reportes/cobertura_curricular_canonica.jsonl": (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        "reportes/cobertura_curricular_fuente.jsonl": (
            "cd37083e0c71151d796cc4b12808a6ffa9c8c5b21c4b99e78f8f54bb0c06fa35"
        ),
        "reportes/competencias_fuente.jsonl": (
            "5d6896b52cbe40efb9303ae6ee9fd1df0afc1b63d9dedeb21c58c686c64d553d"
        ),
        "reportes/habilidades_fuente.jsonl": (
            "7cf0811e43c4fb68957aed2ba7691ae5192791993b72a4dd49ae70b2a997e1ad"
        ),
        "reportes/herramientas_fuente.jsonl": (
            "b694b01617ea61ea2e3e49fd44ca6ea14763666a5f2097530a2e49b5a60cbb85"
        ),
        "reportes/pendientes_curriculares.jsonl": (
            "9d43d7cfca8e3ab5faff788b477243717ee560576b53abba925d110ad38030c5"
        ),
        "reportes/release_gate.json": (
            "a472113334beb01ffad496ca6be5901d0c0ae31e07121b4ea1fdd3d3ad3b47c0"
        ),
    }
    assert canonico.release_gate == {
        "version": "curricular-release-gate/v1",
        "decision": "ALLOW_IMPORT",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "blockers": [],
        "checks": {
            "source_coverage": {
                "ok": True,
                "records": 1,
                "logros_fuente": 1,
                "habilidades_fuente": 1,
            },
            "provenance": {
                "ok": True,
                "missing_competencies": [],
                "missing_skills": [],
                "missing_tools": [],
            },
            "canonical_relations": {"ok": True, "rows": 2, "verified": 2, "missing": []},
            "canonical_references": {"ok": True, "missing": []},
            "chh_graph": {"ok": True, "errors": []},
            "chh_packages": {"ok": True, "errors": []},
            "structural_errors": {"ok": True, "count": 0},
            "pending_preserved": {
                "ok": True,
                "total": 0,
                "by_state": {},
                "expected_unresolved": 0,
                "unresolved_without_pending": 0,
            },
            "approval": {
                "ok": True,
                "pending_decision": 0,
                "unresolved_records": 0,
                "canonical_materialized": True,
            },
        },
        "observability": {
            "source_records": 1,
            "source_logros": 1,
            "canonical_competencies": 1,
            "canonical_skills": 1,
            "canonical_tools": 2,
            "canonical_relations": 2,
            "pending_records": 0,
        },
    }
    assert pendiente.release_gate == {
        "version": "curricular-release-gate/v1",
        "decision": "BLOCK_IMPORT",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "blockers": [
            "UNRESOLVED_CURRICULAR_RECORDS",
            "CANONICAL_MATERIALIZATION_PENDING",
        ],
        "checks": {
            "source_coverage": {
                "ok": True,
                "records": 1,
                "logros_fuente": 1,
                "habilidades_fuente": 1,
            },
            "provenance": {
                "ok": True,
                "missing_competencies": [],
                "missing_skills": [],
                "missing_tools": [],
            },
            "canonical_relations": {"ok": True, "rows": 0, "verified": 0, "missing": []},
            "canonical_references": {"ok": True, "missing": []},
            "chh_graph": {"ok": True, "errors": []},
            "chh_packages": {"ok": True, "errors": []},
            "structural_errors": {"ok": True, "count": 0},
            "pending_preserved": {
                "ok": True,
                "total": 2,
                "by_state": {"PENDIENTE_CATALOGACION": 2},
                "expected_unresolved": 1,
                "unresolved_without_pending": 0,
            },
            "approval": {
                "ok": False,
                "pending_decision": 0,
                "unresolved_records": 2,
                "canonical_materialized": False,
            },
        },
        "observability": {
            "source_records": 1,
            "source_logros": 1,
            "canonical_competencies": 1,
            "canonical_skills": 0,
            "canonical_tools": 0,
            "canonical_relations": 0,
            "pending_records": 2,
        },
    }
    assert pendiente.hallazgos == (
        Hallazgo(
            codigo="HABILIDAD_PENDIENTE_CANONICALIZACION",
            severidad="warning",
            mensaje=(
                "El logro se conserva como habilidad fuente, pero no se encontró una "
                "habilidad canónica con evidencia suficiente."
            ),
            hoja="curso.docx",
            detalle="logro 1: Analizar campañas",
        ),
    )

    corrupta = tmp_path / "corrupta"
    corrupta.mkdir()
    for nombre, columnas in salida.ARCHIVOS_SALIDA:
        (corrupta / nombre).write_text(",".join(columnas) + "\n", encoding="utf-8")
    (corrupta / "curso.csv").write_text("incorrecto\n", encoding="utf-8")
    assert validacion_salida.validar_salidas_curriculares(corrupta, [], {}, {}, {}, {}, set()) == (
        Hallazgo(
            codigo="CSV_ESQUEMA_INVALIDO",
            severidad="error",
            mensaje="El CSV no conserva exactamente el esquema del catálogo.",
            hoja="curso.csv",
            detalle=f"esperado={salida.CURSOS_SCHEMA}; recibido=('incorrecto',)",
        ),
        Hallazgo(
            codigo="COMPETENCIA_FUENTE_NO_AUDITADA",
            severidad="error",
            mensaje="No se generó el reporte de competencias fuente.",
            hoja="reportes/competencias_fuente.jsonl",
        ),
        Hallazgo(
            codigo="HABILIDAD_FUENTE_NO_AUDITADA",
            severidad="error",
            mensaje="No se generó el reporte de habilidades fuente.",
            hoja="reportes/habilidades_fuente.jsonl",
        ),
    )

    historicos = (
        "normalizar_registros_curriculares",
        "_ALIASES_CARRERA",
        "_CARRERAS_POR_NOMBRE",
        "_PALABRAS_NO_EVIDENCIA",
        "ESTADO_PENDIENTE_CATALOGACION",
        "ESTADO_PENDIENTE_PERFIL",
        "ESTADO_REVISION_HUMANA",
        "HerramientaDetectada",
        "NormalizacionCurricular",
        "ResolucionConcepto",
        "TCompetencia",
        "_archivo_origen",
        "_catalogo_curricular",
        "_coincidencias",
        "_competencias_declaradas_por_texto",
        "_competencias_para_logro",
        "_competencias_por_texto",
        "_concepto_decidido",
        "_concepto_declarado",
        "_contexto_curricular",
        "_declaracion_desde_catalogo",
        "_declaraciones",
        "_declaraciones_de_registros",
        "_error",
        "_estado_resolucion_determinista",
        "_evidencia_programa_analitico",
        "_evidencias_herramientas",
        "_evidencias_herramientas_candidatas",
        "_fila_cobertura",
        "_filas_curso",
        "_hash_id",
        "_herramientas_explicitas",
        "_herramientas_llm_nuevas",
        "_id_carrera",
        "_id_competencia_fuente",
        "_logros",
        "_modalidad_curso",
        "_nombre_habilidad",
        "_pendientes_por_relacion_fuente",
        "_propuesta_dict",
        "_registrar_pendiente",
        "_resolver_competencia",
        "_resolver_habilidad_canonica",
        "_seleccionar_competencia_por_puntaje",
        "_source_ref",
        "_texto",
        "_tipo_competencia",
        "_tokens_evidencia",
        "_warning",
    )
    assert len(historicos) == 49
    trazabilidad = (
        "_ALIASES_CARRERA",
        "_CARRERAS_POR_NOMBRE",
        "ESTADO_PENDIENTE_CATALOGACION",
        "ESTADO_PENDIENTE_PERFIL",
        "ESTADO_REVISION_HUMANA",
        "_archivo_origen",
        "_error",
        "_estado_resolucion_determinista",
        "_fila_cobertura",
        "_filas_curso",
        "_hash_id",
        "_id_carrera",
        "_modalidad_curso",
        "_pendientes_por_relacion_fuente",
        "_propuesta_dict",
        "_registrar_pendiente",
        "_source_ref",
        "_texto",
        "_warning",
    )
    for nombre in historicos:
        origen = (
            normalizacion_curricular
            if nombre == "normalizar_registros_curriculares"
            else resolucion_curricular
        )
        assert getattr(salida, nombre) is getattr(origen, nombre)
    for nombre in trazabilidad:
        reexportado = getattr(resolucion_curricular, nombre)
        extraido = getattr(trazabilidad_curricular, nombre)
        assert reexportado is extraido
        assert getattr(salida, nombre) is extraido
        if callable(extraido):
            assert inspect.signature(reexportado) == inspect.signature(extraido)

    validaciones = (
        "COMPETENCIAS_SCHEMA",
        "CURSOS_SCHEMA",
        "HABILIDADES_SCHEMA",
        "HERRAMIENTAS_SCHEMA",
        "COBERTURA_SCHEMA",
        "ARCHIVOS_SALIDA",
        "_ARCHIVOS_CURRICULARES_FINALES",
        "_REPORTES_CURRICULARES_PRE_HITL",
        "_hitl_curricular_completado",
        "_filtrar_outputs_curriculares",
        "_filtrar_estado_publico",
        "validar_salidas_curriculares",
        "evaluar_release_gate",
        "_validar_pendientes_fuente",
        "_conteo_logros_con_descripcion",
        "_ids_unicos",
        "_datos_registros",
    )
    for nombre in validaciones:
        facade = getattr(salida, nombre)
        extraido = getattr(validacion_salida, nombre)
        assert facade is extraido
        if callable(facade):
            assert inspect.signature(facade) == inspect.signature(extraido)

    for nombre in ("evaluar_release_gate", "_validar_pendientes_fuente"):
        extraido = getattr(validacion_salida, nombre)
        normalizador = getattr(release_gate, nombre)
        assert extraido is normalizador
        assert inspect.signature(extraido) == inspect.signature(normalizador)

    source = inspect.getsource(release_gate)
    assert "validacion_salida" not in source
    source = inspect.getsource(trazabilidad_curricular)
    assert "resolucion_curricular" not in source
    assert "silabos.salida" not in source


def _catalogo_por_tipo() -> CatalogoCHH:
    """Catálogo curado con una competencia de cada tipo publicado."""

    return CatalogoCHH(
        competencias=(
            ConceptoCHH(
                "COMP_TEC",
                "Modelar bases de datos",
                "Modelar bases de datos relacionales.",
                "tecnica",
            ),
            ConceptoCHH(
                "COMP_GEN", "Colaborar en equipos", "Colaborar en equipos diversos.", "generica"
            ),
            ConceptoCHH(
                "COMP_ESP", "Analizar mercados", "Analizar mercados internacionales.", "especifica"
            ),
        ),
        habilidades=(
            ConceptoCHH(
                "HAB_TEC",
                "Modelar bases de datos relacionales",
                "Modelar bases de datos relacionales.",
            ),
            ConceptoCHH(
                "HAB_GEN", "Colaborar en equipos diversos", "Colaborar en equipos diversos."
            ),
            ConceptoCHH(
                "HAB_ESP", "Analizar mercados internacionales", "Analizar mercados internacionales."
            ),
            ConceptoCHH(
                "HAB_ESP2",
                "Analizar mercados de servicios internacionales",
                "Analizar mercados de servicios internacionales.",
            ),
        ),
        herramientas=(ConceptoCHH("HERR_SQL", "SQL", "Lenguaje de consulta."),),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def _registro_por_tipo(id_silabo: str, id_curso: str) -> dict[str, object]:
    """Registro con un logro técnico, uno genérico y dos específicos."""

    registro = _registro()
    registro["id_silabo"] = id_silabo
    registro["id_curso"] = id_curso
    datos = registro["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"orden": "1", "descripcion": "Modelar bases de datos relacionales"},
        {"orden": "2", "descripcion": "Colaborar en equipos diversos"},
        {"orden": "3", "descripcion": "Analizar mercados internacionales"},
        {"orden": "4", "descripcion": "Analizar mercados de servicios internacionales"},
    ]
    datos["competencias_declaradas"] = [
        {
            "orden": "1",
            "nombre": "Modelar bases de datos",
            "descripcion": "Modelar bases de datos relacionales.",
        },
        {
            "orden": "2",
            "nombre": "Colaborar en equipos",
            "descripcion": "Colaborar en equipos diversos.",
        },
        {
            "orden": "3",
            "nombre": "Analizar mercados",
            "descripcion": "Analizar mercados internacionales.",
        },
    ]
    datos["herramientas_evidencia"] = []
    return registro


def _filas_y_encabezado(salida: Path, nombre: str) -> tuple[list[str], list[dict[str, str]]]:
    with (salida / nombre).open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        return list(lector.fieldnames or []), list(lector)


def test_catalogo_publicado_son_logros_con_descripcion_derivada(tmp_path: Path) -> None:
    """El catálogo publicado son los logros, no las habilidades canónicas."""

    salida = tmp_path / "NOR_TEST" / "salidas"
    construir_salidas_curriculares(
        [_registro_por_tipo("SIL_1", "CUR_1"), _registro_por_tipo("SIL_2", "CUR_2")],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo_por_tipo(),
    )

    assert (salida / "catalogo_logros.csv").is_file()
    assert not (salida / "catalogo_habilidades.csv").exists()

    encabezado, logros = _filas_y_encabezado(salida, "catalogo_logros.csv")
    assert encabezado == ["id_logro", "nombre_logro", "descripcion_breve"]

    for fila in logros:
        nombre = fila["nombre_logro"]
        derivada = "Capacidad para " + nombre[0].lower() + nombre[1:]
        if not derivada.endswith("."):
            derivada += "."
        assert fila["id_logro"] == hashed("LOGRO", nombre)
        assert fila["descripcion_breve"] == derivada

    # Dos sílabos que declaran el mismo logro normalizado publican UNA sola fila.
    assert [fila["nombre_logro"] for fila in logros] == ["Modelar bases de datos relacionales"]
    assert [fila["id_logro"] for fila in logros] == [
        hashed("LOGRO", "Modelar bases de datos relacionales")
    ]


def test_cobertura_lleva_logro_solo_en_competencias_tecnicas(tmp_path: Path) -> None:
    """La cobertura técnica lleva logro; la genérica y la específica no."""

    salida = tmp_path / "NOR_TEST" / "salidas"
    construir_salidas_curriculares(
        [_registro_por_tipo("SIL_1", "CUR_1")],
        _validacion(),
        tmp_path / "NOR_TEST",
        _catalogo_por_tipo(),
    )

    encabezado, cobertura = _filas_y_encabezado(salida, "cobertura_curricular.csv")
    assert encabezado == [
        "id_cob_curricular",
        "id_curso",
        "id_silabo",
        "id_competencia",
        "id_logro",
        "id_herramienta",
    ]

    logro_tecnico = hashed("LOGRO", "Modelar bases de datos relacionales")
    esperado_por_competencia = {
        "COMP_TEC": logro_tecnico,
        "COMP_GEN": "",
        "COMP_ESP": "",
    }
    for fila in cobertura:
        assert fila["id_logro"] == esperado_por_competencia[fila["id_competencia"]]
        assert fila["id_cob_curricular"] == hashed(
            "COB_CUR",
            fila["id_curso"],
            fila["id_silabo"],
            fila["id_competencia"],
            fila["id_logro"],
            fila["id_herramienta"],
        )

    assert [fila["id_competencia"] for fila in cobertura if fila["id_logro"]] == ["COMP_TEC"]

    # Dos logros específicos activan la misma competencia específica: sin logro, la
    # cobertura colapsa a una sola fila por (curso, sílabo, competencia, herramienta).
    sin_logro = [fila for fila in cobertura if not fila["id_logro"]]
    assert len(sin_logro) == 2
    assert {
        (fila["id_curso"], fila["id_silabo"], fila["id_competencia"], fila["id_herramienta"])
        for fila in sin_logro
    } == {
        ("CUR_1", "SIL_1", "COMP_GEN", ""),
        ("CUR_1", "SIL_1", "COMP_ESP", ""),
    }
