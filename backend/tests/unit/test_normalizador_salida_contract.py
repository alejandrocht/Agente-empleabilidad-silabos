"""Regression tests for the public curricular-output seam."""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import re
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
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
            "f3e32c125374666980b1d2afe3d06d8179647918b5591d70e113dad36d4ae89a"
        ),
        "catalogo_habilidades.csv": (
            "0e4d58da1c6385d5d7decbc82b918a24be42b1bf7a614bfc78b8bc08ae77dc3b"
        ),
        "catalogo_herramientas.csv": (
            "b7e8db9bb823a80d174720b9b5c606d03bb71a35fe281835c306956cf67e405a"
        ),
        "cobertura_curricular.csv": (
            "c5c4f6ef01ab1bbf81d33ec4234c6d52a2d5d90c60cfb0413d8e0f0bb080e0ff"
        ),
        "curso.csv": "b9735fa0466a8504a53083a6815b03db2a1c60eac1abfe93033e9561293817dd",
        "reportes/candidatos_curriculares.json": (
            "eb33bb535b1ffe0fc8b4acd93e291027ffb0cbf3ca2a03f0f705741df11d82eb"
        ),
        "reportes/cobertura_curricular_canonica.jsonl": (
            "52025738b253d279fa73528a724898b11e981375ab5db36c4647aa440592d449"
        ),
        "reportes/cobertura_curricular_fuente.jsonl": (
            "f72ae3ed1ddef5ae04dca5288a027d25e8e652212b155ab3b2c4ab3b606ca449"
        ),
        "reportes/competencias_fuente.jsonl": (
            "5d6896b52cbe40efb9303ae6ee9fd1df0afc1b63d9dedeb21c58c686c64d553d"
        ),
        "reportes/habilidades_fuente.jsonl": (
            "f0c503d5ce3eee6aae73891b4d8e95b1a6a1486ad05a9c3866f1798aefe04995"
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
    }
    assert _hashes_de_artefactos(tmp_path / "pending" / "NOR_TEST" / "salidas") == {
        "reportes/candidatos_curriculares.json": (
            "04d99b769bddeff50af1c13b353fbee4277fad95cbb24a45939d1f9069d3fae0"
        ),
        "reportes/cobertura_curricular_canonica.jsonl": (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
        "reportes/cobertura_curricular_fuente.jsonl": (
            "698c42dc9ed7c256591ca61fd7fcaae6f3673865f32ede321fd35f0594c7115e"
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
            "18531528b183c152aa4c6c9437a093761b995e7cb9e906f0c127819b985a428a"
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
    assert validacion_salida.validar_salidas_curriculares(
        corrupta, [], {}, {}, {}, {}, set()
    ) == (
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
