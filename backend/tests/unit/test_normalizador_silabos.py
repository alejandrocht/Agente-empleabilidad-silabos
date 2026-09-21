"""Pruebas del contrato y staging curricular."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from docx import Document
from openai import LengthFinishReasonError

from agente.config import settings
from agente.normalizador.modelos import ProgresoLimpiezaLLM
from agente.normalizador.silabos import analista_tecnico, limpieza
from agente.normalizador.silabos.entrada import validar_archivo
from agente.normalizador.silabos.limpieza import (
    _campo_pdf_metadata,
    _competencias_pdf,
    _extraer_docx,
    _extraer_pdf,
    _extraer_programa_analitico_geometrico_pdf,
    _extraer_programa_analitico_pdf,
    _logros_pdf,
    _texto_celda_pdf,
    limpiar_archivo,
)


def test_import_limpieza_does_not_load_retired_curriculum_modules() -> None:
    probe = """
import sys
from agente.normalizador.silabos import limpieza

for module_name in (
    "agente.normalizador.silabos.salida",
    "agente.normalizador.silabos.analista_llm",
    "agente.normalizador.embeddings",
):
    assert module_name not in sys.modules, module_name
"""
    resultado = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


def _crear_docx(ruta: Path) -> None:
    documento = Document()
    metadata = documento.add_table(rows=1, cols=2)
    metadata.cell(0, 0).text = "Curso"
    metadata.cell(0, 1).text = "Diseño de bases de datos"
    sumilla = documento.add_table(rows=2, cols=1)
    sumilla.cell(0, 0).text = "Sumilla"
    sumilla.cell(1, 0).text = "Modelamiento de bases de datos relacionales."
    competencia = documento.add_table(rows=2, cols=3)
    competencia.cell(0, 0).text = "Competencias genéricas"
    competencia.cell(0, 1).text = "Descripción"
    competencia.cell(0, 2).text = "Código"
    competencia.cell(1, 0).text = "Diseño de bases de datos"
    competencia.cell(1, 1).text = "Modelar bases de datos relacionales."
    competencia.cell(1, 2).text = "G1"
    logro = documento.add_table(rows=2, cols=3)
    logro.cell(0, 0).text = "Logro de aprendizaje general"
    logro.cell(0, 1).text = "Descripción"
    logro.cell(0, 2).text = "Competencias"
    logro.cell(1, 0).text = "L1"
    logro.cell(1, 1).text = "Modelar bases de datos relacionales"
    logro.cell(1, 2).text = "G1"
    documento.save(str(ruta))


def _crear_docx_con_logro_verticalmente_combinado(ruta: Path) -> None:
    """Replica una fila L3 cuyo XML usa ``w:vMerge`` en las tres columnas."""

    documento = Document()
    tabla = documento.add_table(rows=4, cols=3)
    for celda, valor in zip(
        tabla.rows[0].cells,
        ("Logro de aprendizaje general", "Descripción", "Competencias"),
        strict=True,
    ):
        celda.text = valor
    tabla.cell(1, 0).text = "L3"
    tabla.cell(1, 1).text = "Desarrollar el texto completo y verificable del logro L3."
    tabla.cell(1, 2).text = "E3"
    for columna in range(3):
        tabla.cell(1, columna).merge(tabla.cell(3, columna))
    documento.save(str(ruta))


def test_valida_y_limpia_docx_con_carrera_y_periodo(tmp_path: Path) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")

    assert validacion.valida is True
    assert validacion.carrera == "INGENIERIA_DE_SISTEMAS"
    assert validacion.archivos[0].formato == "docx"

    ejecucion = tmp_path / "ejecucion"
    resultado = limpiar_archivo(fuente, ejecucion, validacion)

    assert resultado.registros == 1
    assert resultado.publicable is True
    assert resultado.relaciones == 2
    registro = json.loads((ejecucion / "limpios" / "silabos.jsonl").read_text(encoding="utf-8"))
    assert registro["datos"]["curso"] == "Diseño de bases de datos"
    assert registro["datos"]["logros_especificos"][0] == {
        "orden": "1",
        "descripcion": "Modelar bases de datos relacionales",
        "codigos_competencia": ["G1"],
        "texto_evidencia": "Modelar bases de datos relacionales",
    }
    assert {
        "salidas/curso.csv",
        "salidas/silabo.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_logros.csv",
        "salidas/cobertura_curricular.csv",
        "propuestas_tecnicas.jsonl",
        "analisis_tecnico.json",
        "salidas/reportes/release_gate.json",
    } <= {output["archivo"] for output in resultado.outputs}
    schemas = {
        "curso.csv": [
            "id_curso",
            "nombre_curso",
            "coordinador",
            "creditos",
            "nivel",
            "tipo_curso",
            "codigo_curso",
            "id_carrera",
        ],
        "silabo.csv": [
            "id_silabo",
            "codigo_silabo",
            "sumilla",
            "id_curso",
            "periodo_academico",
        ],
        "catalogo_competencias.csv": [
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve_competencia",
            "tipo_competencia",
            "codigo_competencia",
        ],
        "catalogo_logros.csv": ["id_logro", "logro"],
        "cobertura_curricular.csv": [
            "id_cob_curricular",
            "id_curso",
            "id_silabo",
            "id_competencia",
            "id_logro",
        ],
    }
    for nombre, esperado in schemas.items():
        with (ejecucion / "salidas" / nombre).open(encoding="utf-8-sig", newline="") as archivo:
            assert next(csv.reader(archivo)) == esperado


def test_extrae_metadatos_estructurados_docx_y_conserva_coordinadores(tmp_path: Path) -> None:
    fuente = tmp_path / "metadatos.docx"
    documento = Document()
    metadata = documento.add_table(rows=8, cols=2)
    for fila, etiqueta, valor in (
        (0, "Asignatura", "Arquitectura de software"),
        (1, "Coordinador", "Ana Pérez"),
        (2, "Coordinador", "Bruno Díaz"),
        (3, "Créditos", "4"),
        (4, "Nivel", "Sexto"),
        (5, "Tipo de asignatura", "Obligatorio"),
        (6, "Modalidad", "Híbrida"),
        (7, "Código", "SIS601"),
    ):
        metadata.cell(fila, 0).text = etiqueta
        metadata.cell(fila, 1).text = valor
    documento.save(str(fuente))

    datos = _extraer_docx(fuente, fuente.name, "INGENIERIA_DE_SISTEMAS", "2026-1")["datos"]

    assert isinstance(datos, dict)
    assert datos["curso"] == "Arquitectura de software"
    assert datos["ciclo"] == "Sexto"
    assert datos["codigo_curso"] == "SIS601"
    campos = ("nombre_curso", "coordinador", "creditos", "nivel", "tipo_curso")
    assert {campo: datos[campo] for campo in campos} == {
        "nombre_curso": "Arquitectura de software",
        "coordinador": "Ana Pérez | Bruno Díaz",
        "creditos": "4",
        "nivel": "Sexto",
        "tipo_curso": "Híbrido",
    }


def test_modalidad_no_se_infiere_de_tipo_de_asignatura_o_naturaleza(tmp_path: Path) -> None:
    fuente = tmp_path / "curso-sin-modalidad.docx"
    documento = Document()
    metadata = documento.add_table(rows=3, cols=2)
    for fila, etiqueta, valor in (
        (0, "Asignatura", "Taller de sistemas complejos"),
        (1, "Tipo de asignatura", "Electiva"),
        (2, "Naturaleza", "Obligatoria"),
    ):
        metadata.cell(fila, 0).text = etiqueta
        metadata.cell(fila, 1).text = valor
    documento.save(str(fuente))

    datos = _extraer_docx(fuente, fuente.name, "PRUEBA", "2031-2")["datos"]

    assert isinstance(datos, dict)
    assert datos["tipo_curso"] == ""


def test_extrae_programa_docx_con_y_sin_celdas_combinadas_horizontalmente(
    tmp_path: Path,
) -> None:
    fuente = tmp_path / "programa.docx"
    documento = Document()
    normal = documento.add_table(rows=2, cols=4)
    for columna, valor in enumerate(("Semana", "Tema", "Contenido", "Evaluación")):
        normal.cell(0, columna).text = valor
    for columna, valor in enumerate(("1", "Tema normal", "Contenido normal", "")):
        normal.cell(1, columna).text = valor

    combinado = documento.add_table(rows=2, cols=5)
    combinado.cell(0, 0).merge(combinado.cell(0, 1)).text = "Semana"
    for columna, valor in enumerate(("Tema", "Contenido", "Evaluación"), start=2):
        combinado.cell(0, columna).text = valor
    combinado.cell(1, 0).merge(combinado.cell(1, 1)).text = "2"
    for columna, valor in enumerate(("Tema combinado", "Contenido combinado", ""), start=2):
        combinado.cell(1, columna).text = valor
    documento.save(str(fuente))

    datos = _extraer_docx(fuente, fuente.name, "PRUEBA", "2031-2")["datos"]

    assert isinstance(datos, dict)
    assert datos["programa_analitico"] == [
        "Tema normal | Contenido normal",
        "Tema combinado | Contenido combinado",
    ]


def test_publica_logros_detectados_durante_la_extraccion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    progresos: list[ProgresoLimpiezaLLM] = []
    monkeypatch.setattr(
        analista_tecnico,
        "inferir_competencias_tecnicas",
        lambda *_args, **_kwargs: [],
    )

    limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        usar_llm=True,
        configuracion_curricular=settings.configuracion_normalizador_curricular(),
        al_actualizar_progreso_llm=progresos.append,
    )

    progreso_extraccion = next(progreso for progreso in progresos if progreso.fase == "extrayendo")
    assert progreso_extraccion.logros_detectados == 1
    assert progreso_extraccion.logros_totales == 1
    assert progreso_extraccion.silabos_detectados == 1
    assert progreso_extraccion.silabos_procesados == 0
    assert progreso_extraccion.silabos_totales == 1
    assert progreso_extraccion.eventos[-1].mensaje == (
        "Logros detectados: 1. Sílabos detectados: 1/1."
    )


def test_technical_mode_reuses_extracted_records_and_keeps_proposals_pending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    configuracion = replace(
        settings.configuracion_normalizador_curricular(),
        ruta_catalogo_tecnico="catalogo-tecnico.xlsx",
    )
    parser_calls: list[None] = []
    extracted_records: list[dict[str, object]] = []
    technical_records: list[list[dict[str, object]]] = []
    original_parser = limpieza._extraer_docx
    propuesta: dict[str, object] = {
        "id_propuesta": "PROP_TEC_TEST",
        "estado_aprobacion": "PENDIENTE_APROBACION",
        "nombre_competencia": "Competencia técnica propuesta",
    }

    def parse_once(ruta: Path, nombre: str, carrera: str, periodo: str) -> dict[str, object]:
        parser_calls.append(None)
        registro = original_parser(ruta, nombre, carrera, periodo)
        extracted_records.append(registro)
        return registro

    def inferir(
        registros: list[dict[str, object]], *_args: object, **_kwargs: object
    ) -> list[dict[str, object]]:
        technical_records.append(registros)
        return [propuesta]

    technical_builder = Mock(wraps=limpieza.construir_salidas_tecnicas)

    monkeypatch.setattr(limpieza, "_extraer_docx", parse_once)
    monkeypatch.setattr(analista_tecnico, "inferir_competencias_tecnicas", inferir)
    monkeypatch.setattr(limpieza, "construir_salidas_tecnicas", technical_builder)

    ejecucion = tmp_path / "ejecucion"
    resultado = limpiar_archivo(
        fuente,
        ejecucion,
        validacion,
        usar_llm=True,
        configuracion_curricular=configuracion,
    )

    assert len(parser_calls) == 1
    assert len(extracted_records) == 1
    assert len(technical_records) == 1
    assert technical_records[0][0] is extracted_records[0]
    assert technical_records[0] is technical_builder.call_args.args[0]
    propuestas = [
        json.loads(line)
        for line in (ejecucion / "salidas" / "reportes" / "propuestas_tecnicas.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert propuestas == [propuesta]
    assert propuestas[0]["estado_aprobacion"] == "PENDIENTE_APROBACION"
    assert json.loads(
        (ejecucion / "salidas" / "reportes" / "analisis_tecnico.json").read_text(encoding="utf-8")
    ) == {
        "estado": "COMPLETADO",
        "modo_analista": "technical",
        "propuestas_pendientes": 1,
    }
    assert {
        "salidas/curso.csv",
        "salidas/silabo.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_logros.csv",
        "salidas/cobertura_curricular.csv",
        "propuestas_tecnicas.jsonl",
        "analisis_tecnico.json",
        "salidas/reportes/release_gate.json",
    } <= {output["archivo"] for output in resultado.outputs}
    assert resultado.publicable is False
    assert resultado.pendientes == 1
    with (ejecucion / "salidas" / "catalogo_competencias.csv").open(
        encoding="utf-8-sig", newline=""
    ) as archivo:
        assert {fila["tipo_competencia"] for fila in csv.DictReader(archivo)} == {"generica"}
    gate = json.loads(
        (ejecucion / "salidas" / "reportes" / "release_gate.json").read_text(encoding="utf-8")
    )
    assert gate["decision"] == "BLOCK_IMPORT"
    assert gate["checks"]["approval"]["pending_count"] == 1
    candidatos = ejecucion / "salidas" / "reportes" / "candidatos_curriculares.json"
    assert not candidatos.exists()


def test_technical_mode_without_llm_builds_deterministic_contract_without_proposals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    configuracion = replace(
        settings.configuracion_normalizador_curricular(),
        usar_llm=False,
        ruta_catalogo_tecnico="catalogo-tecnico.xlsx",
    )
    extracted_records: list[dict[str, object]] = []
    original_parser = limpieza._extraer_docx

    def parse_once(ruta: Path, nombre: str, carrera: str, periodo: str) -> dict[str, object]:
        registro = original_parser(ruta, nombre, carrera, periodo)
        extracted_records.append(registro)
        return registro

    inferir = Mock(side_effect=AssertionError("Technical inference must not run without LLM"))
    construir_llm = Mock(side_effect=AssertionError("LLM construction must not run"))
    technical_builder = Mock(wraps=limpieza.construir_salidas_tecnicas)

    monkeypatch.setattr(limpieza, "_extraer_docx", parse_once)
    monkeypatch.setattr(analista_tecnico, "inferir_competencias_tecnicas", inferir)
    monkeypatch.setattr(analista_tecnico, "obtener_llm", construir_llm)
    monkeypatch.setattr(limpieza, "construir_salidas_tecnicas", technical_builder)

    ejecucion = tmp_path / "ejecucion"
    resultado = limpiar_archivo(
        fuente,
        ejecucion,
        validacion,
        usar_llm=False,
        configuracion_curricular=configuracion,
    )

    assert inferir.call_count == 0
    assert construir_llm.call_count == 0
    assert len(extracted_records) == 1
    assert technical_builder.call_args.args[0][0] is extracted_records[0]
    assert {
        "salidas/curso.csv",
        "salidas/silabo.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_logros.csv",
        "salidas/cobertura_curricular.csv",
    } <= {output["archivo"] for output in resultado.outputs}
    assert not (ejecucion / "salidas" / "contenido_semanal.csv").exists()

    reportes = ejecucion / "salidas" / "reportes"
    assert (reportes / "propuestas_tecnicas.jsonl").read_text(encoding="utf-8") == ""
    assert json.loads((reportes / "analisis_tecnico.json").read_text(encoding="utf-8")) == {
        "estado": "COMPLETADO",
        "modo_analista": "technical",
        "modo_ejecucion": "DETERMINISTICO_SIN_LLM",
        "propuestas_pendientes": 0,
    }
    assert resultado.publicable is True
    assert resultado.release_gate["decision"] == "ALLOW_IMPORT"
    checks = resultado.release_gate["checks"]
    assert isinstance(checks, dict)
    deterministic_outputs = checks["deterministic_outputs"]
    approval = checks["approval"]
    assert isinstance(deterministic_outputs, dict)
    assert isinstance(approval, dict)
    assert deterministic_outputs["ok"] is True
    assert approval["ok"] is True


def test_technical_analyzer_classifies_length_truncation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    configuracion = replace(
        settings.configuracion_normalizador_curricular(),
        ruta_catalogo_tecnico="catalogo-tecnico.xlsx",
    )
    monkeypatch.setattr(
        analista_tecnico,
        "inferir_competencias_tecnicas",
        Mock(side_effect=LengthFinishReasonError(completion=Mock())),
    )

    ejecucion = tmp_path / "ejecucion"
    resultado = limpiar_archivo(
        fuente,
        ejecucion,
        validacion,
        usar_llm=True,
        configuracion_curricular=configuracion,
    )

    hallazgo = next(
        hallazgo
        for hallazgo in resultado.hallazgos
        if hallazgo.codigo.startswith("ANALISTA_TECNICO_")
    )
    assert hallazgo.codigo == "ANALISTA_TECNICO_RESPUESTA_TRUNCADA"
    assert hallazgo.mensaje == (
        "El analista técnico respondió, pero su salida fue truncada al alcanzar "
        "el límite de contexto/longitud; se conservan los resultados deterministas."
    )
    analisis = json.loads(
        (ejecucion / "salidas" / "reportes" / "analisis_tecnico.json").read_text(encoding="utf-8")
    )
    assert analisis["estado"] == "FALLBACK_DETERMINISTA"
    assert resultado.publicable is False
    assert resultado.release_gate["decision"] == "BLOCK_IMPORT"
    blockers = resultado.release_gate["blockers"]
    assert isinstance(blockers, list)
    assert "TECHNICAL_ANALYSIS_FAILED" in blockers


def test_technical_analyzer_classifies_unrelated_failure_as_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    configuracion = replace(
        settings.configuracion_normalizador_curricular(),
        ruta_catalogo_tecnico="catalogo-tecnico.xlsx",
    )
    monkeypatch.setattr(
        analista_tecnico,
        "inferir_competencias_tecnicas",
        Mock(side_effect=RuntimeError("fallo no relacionado")),
    )

    resultado = limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        usar_llm=True,
        configuracion_curricular=configuracion,
    )

    assert any(
        hallazgo.codigo == "ANALISTA_TECNICO_NO_DISPONIBLE" for hallazgo in resultado.hallazgos
    )


def test_technical_analyzer_without_valid_proposals_records_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    configuracion = replace(
        settings.configuracion_normalizador_curricular(),
        ruta_catalogo_tecnico="catalogo-tecnico.xlsx",
    )

    def without_valid_proposals(*_args: object, **kwargs: object) -> list[dict[str, object]]:
        auditoria = kwargs["auditoria"]
        assert isinstance(auditoria, list)
        auditoria.append(
            {
                "codigo": "SILABO_SIN_PROPUESTA_TECNICA",
                "id_silabo": "SIL_TEST",
                "mensaje": "El sílabo no produjo ninguna propuesta técnica válida.",
            }
        )
        return []

    monkeypatch.setattr(
        analista_tecnico,
        "inferir_competencias_tecnicas",
        without_valid_proposals,
    )

    ejecucion = tmp_path / "ejecucion"
    resultado = limpiar_archivo(
        fuente,
        ejecucion,
        validacion,
        usar_llm=True,
        configuracion_curricular=configuracion,
    )

    assert all(
        (ejecucion / "salidas" / nombre).is_file()
        for nombre in (
            "curso.csv",
            "silabo.csv",
            "catalogo_competencias.csv",
            "catalogo_logros.csv",
            "cobertura_curricular.csv",
        )
    )
    assert not (ejecucion / "salidas" / "contenido_semanal.csv").exists()
    assert any(
        hallazgo.codigo == "SILABO_SIN_PROPUESTA_TECNICA" and hallazgo.severidad == "warning"
        for hallazgo in resultado.hallazgos
    )
    assert (
        json.loads(
            (ejecucion / "salidas" / "reportes" / "analisis_tecnico.json").read_text(
                encoding="utf-8"
            )
        )["estado"]
        == "COMPLETADO_CON_ADVERTENCIAS"
    )
    gate = json.loads(
        (ejecucion / "salidas" / "reportes" / "release_gate.json").read_text(encoding="utf-8")
    )
    assert gate["decision"] == "BLOCK_IMPORT"
    assert gate["checks"]["analysis"]["ok"] is False
    assert "TECHNICAL_ANALYSIS_INCOMPLETE" in gate["blockers"]
    analisis = json.loads(
        (ejecucion / "salidas" / "reportes" / "analisis_tecnico.json").read_text(encoding="utf-8")
    )
    assert analisis["advertencias"][0]["codigo"] == "SILABO_SIN_PROPUESTA_TECNICA"


def test_extrae_una_sola_fila_logica_para_logro_con_vmerge(tmp_path: Path) -> None:
    fuente = tmp_path / "MARKETING_SOCIAL.docx"
    _crear_docx_con_logro_verticalmente_combinado(fuente)

    registro = limpieza._extraer_docx(fuente, fuente.name, "MARKETING", "2026-1")
    datos = registro["datos"]
    assert isinstance(datos, dict)
    logros = datos["logros_especificos"]
    assert isinstance(logros, list)

    assert [logro["orden"] for logro in logros] == ["1"]
    assert logros[0] == {
        "orden": "1",
        "descripcion": "Desarrollar el texto completo y verificable del logro .",
        "codigos_competencia": ["E3"],
        "texto_evidencia": "Desarrollar el texto completo y verificable del logro .",
    }


def test_rechaza_ruta_insegura_en_zip(tmp_path: Path) -> None:
    fuente = tmp_path / "curriculo.zip"
    with zipfile.ZipFile(fuente, "w") as paquete:
        paquete.writestr("../fuera.docx", b"no es un docx")

    validacion = validar_archivo(fuente, "Marketing", "2030-1")

    assert validacion.valida is False
    assert any(hallazgo.codigo == "RUTA_ZIP_INSEGURA" for hallazgo in validacion.hallazgos)


def test_zip_inseguro_no_materializa_archivos(tmp_path: Path) -> None:
    fuente = tmp_path / "curriculo.zip"
    with zipfile.ZipFile(fuente, "w") as paquete:
        paquete.writestr("../fuera.docx", b"no es un docx")

    validacion = validar_archivo(fuente, "Marketing", "2030-1")
    destino = tmp_path / "fuentes_curriculares"

    assert validacion.valida is False
    assert limpieza._materializar(fuente, destino, validacion.archivos) == {}
    assert not destino.exists()


def test_ignora_silenciosamente_metadatos_de_macos_en_zip(tmp_path: Path) -> None:
    docx = tmp_path / "curso.docx"
    _crear_docx(docx)
    fuente = tmp_path / "curriculo.zip"
    with zipfile.ZipFile(fuente, "w") as paquete:
        paquete.write(docx, "MARKETING/curso.docx")
        paquete.writestr("__MACOSX/MARKETING/._curso.docx", b"metadata")

    validacion = validar_archivo(fuente, "Marketing", "2030-1")

    assert validacion.valida is True
    assert [archivo.nombre for archivo in validacion.archivos] == ["MARKETING/curso.docx"]
    assert validacion.hallazgos == ()


def test_campo_pdf_metadata_detiene_coordinador_en_docentes_y_metadatos() -> None:
    texto = """
    I. Información general
    Coordinador Ana Pérez
                Bruno Díaz
    Docentes
    Carla Docente
    Área Ingeniería
    Modalidad Presencial
    Naturaleza Obligatoria
    Requisito Ninguno
    Horas de teoría 2
    Horas de práctica 2
    II. Sumilla
    """

    coordinador = _campo_pdf_metadata(texto, r"Coordinador", continuacion=True)

    assert coordinador == "Ana Pérez | Bruno Díaz"
    assert "Docentes" not in coordinador
    assert "Carla" not in coordinador


def test_parser_pdf_uses_references_only_to_split_rows() -> None:
    competencias = _competencias_pdf(
        "Competencias específicas Gestión estratégica Diseñar estrategias de marketing EE"
    )
    logros = _logros_pdf(
        "Logros de aprendizaje específicos L1 Diseñar una estrategia de marketing EE"
    )

    assert competencias[0]["orden"] == "1"
    assert competencias[0]["codigo"] == "EE"
    assert competencias[0]["tipo"] == "especifica"
    assert competencias[0]["texto_evidencia"] == (
        "Gestión estratégica Diseñar estrategias de marketing"
    )
    assert logros == [
        {
            "orden": "1",
            "descripcion": "Diseñar una estrategia de marketing",
            "codigos_competencia": ["EE"],
            "texto_evidencia": "Diseñar una estrategia de marketing",
        }
    ]


def test_extrae_pdf_layout_i_vi_y_conserva_vii_viii_solo_en_fuente(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = """
    I.      Información general
    Asignatura                      Sistemas de Inteligencia Empresarial
    Tipo de asignatura              Obligatorio
    Modalidad                       Presencial
    Código                          650062
    Nivel                           Séptimo
    Créditos                        4
    Coordinador                     Ana Pérez
                                    Bruno Díaz
    II.     Sumilla
    Esta asignatura desarrolla inteligencia de negocios para evaluar entornos organizacionales.
    III.    Competencias
                                        Competencias genéricas
     Solución     creativa     de    Toma decisiones estratégicas para generar un cambio       G2
     problemas                       forma innovadora.
    IV.     Logros de aprendizaje
                              Logro de aprendizaje general
    El estudiante construye conceptos de inteligencia de negocios.
                           Logros de aprendizaje específicos
     L1    Detecta problemas dentro del contexto del negocio.                              G2
     L2    Utiliza técnicas de modelamiento para la arquitectura de datos.                 G2
     L3    Construye procesos de extracción, transformación y carga.                       G2
    V.      Estrategia de enseñanza
                              Metodologías y técnicas de enseñanza
    Clase magistral y ejercicios prácticos.
                                        Recursos de aprendizaje
    Presentaciones del curso, herramientas de ETL y plataformas para análisis de datos.
    VI.     Programa analítico
    Semana               Tema                                  Contenido             \
    Evaluación
     4                  ETL             Extracción, Transformación y Carga. Lab SQL-SSIS \
    1
     7                  Gobierno        Laboratorio ETL - Analysis Services.
    10                 Procesos         Laboratorio Power BI - Conexión a SQL
    13                 Tendencias      Modelos predictivos en Excel, Orange y Python.
    VII.    Evaluación
    La nota final se calcula con evaluaciones y uso de herramientas basadas en IA.
    VIII.   Referencias
    https://bibliografia.example/referencia
    """
    plain = "\n".join(
        (
            "I. Información general Asignatura Sistemas de Inteligencia Empresarial",
            (
                "Tipo de asignatura Obligatorio Código 650062 Nivel Séptimo Créditos 4 "
                "Coordinador Ana Pérez Bruno Díaz"
            ),
            "II. Sumilla III. Competencias Competencias genéricas",
            "Solución creativa de problemas Toma decisiones estratégicas para generar",
            "un cambio de forma innovadora. G2",
            "Esta asignatura desarrolla inteligencia de negocios para evaluar entornos",
            "organizacionales.",
            "IV. Logros de aprendizaje Logro de aprendizaje general El estudiante construye",
            "conceptos de inteligencia de negocios. Logros de aprendizaje específicos",
            "L1 Detecta problemas dentro del contexto del negocio. G2",
            "L2 Utiliza técnicas de modelamiento para la arquitectura de datos. G2",
            "L3 Construye procesos de extracción, transformación y carga. G2",
            "V. Estrategia de enseñanza Metodologías y técnicas de enseñanza Clase",
            "magistral y ejercicios prácticos. Recursos de aprendizaje Presentaciones",
            "del curso, herramientas de ETL y plataformas para análisis de datos.",
            "VI. Programa analítico Semana Tema Contenido Evaluación 4 ETL Extracción,",
            "Transformación y Carga. Lab SQL-SSIS 1 7 Gobierno Laboratorio ETL -",
            "Analysis Services. 10 Procesos Laboratorio Power BI - Conexión a SQL",
            "13 Tendencias Modelos predictivos en Excel, Orange y Python.",
            "VII. Evaluación La nota final se calcula con evaluaciones y uso de",
            "herramientas basadas en IA.",
            "VIII. Referencias https://bibliografia.example/referencia",
        )
    )

    class _PaginaFalsa:
        def extract_text(self, extraction_mode: str | None = None) -> str:
            return layout if extraction_mode == "layout" else plain

    class _LectorFalso:
        pages = [_PaginaFalsa()]

    monkeypatch.setattr(limpieza, "PdfReader", lambda _ruta: _LectorFalso())
    fuente = tmp_path / "sistemas.pdf"
    fuente.write_bytes(b"pdf-falso")

    registro = _extraer_pdf(fuente, fuente.name, "SISTEMAS", "2026-1")
    datos = registro["datos"]
    assert isinstance(datos, dict)
    assert datos["curso"] == "Sistemas de Inteligencia Empresarial"
    assert datos["nombre_curso"] == "Sistemas de Inteligencia Empresarial"
    assert datos["tipo_curso"] == "Presencial"
    assert datos["codigo_curso"] == "650062"
    assert datos["nivel"] == "Séptimo"
    assert datos["creditos"] == "4"
    assert datos["coordinador"] == "Ana Pérez | Bruno Díaz"
    assert datos["sumilla"]
    assert datos["competencias_declaradas"] == [
        {
            "orden": "1",
            "nombre": "Solución creativa de problemas",
            "descripcion": "Toma decisiones estratégicas para generar un cambio forma innovadora.",
            "codigo": "G2",
            "tipo": "generica",
            "texto_evidencia": (
                "Solución creativa de Toma decisiones estratégicas para generar un cambio "
                "problemas forma innovadora."
            ),
        }
    ]
    assert [logro["orden"] for logro in datos["logros_especificos"]] == ["1", "2", "3"]
    assert all("G2" not in logro["texto_evidencia"] for logro in datos["logros_especificos"])
    assert datos["metodologias_ensenanza"] == "Clase magistral y ejercicios prácticos."
    assert "herramientas de ETL" in datos["recursos_aprendizaje"]
    assert len(datos["programa_analitico"]) == 4
    assert {fila["semana"] for fila in datos["programa_analitico_detalle"]} == {
        "4",
        "7",
        "10",
        "13",
    }
    assert "SQL-SSIS" in " ".join(datos["programa_analitico"])
    assert "Power BI" in " ".join(datos["programa_analitico"])
    assert "herramientas_evidencia" not in datos
    assert "Evaluación" not in datos["texto_relevante"]
    assert "bibliografia.example" not in datos["texto_relevante"]
    assert "bibliografia.example" in datos["texto_fuente"]
    assert "G2" not in datos["texto_fuente"]


def test_programa_pdf_separa_columnas_y_descarta_evaluacion_intermedia() -> None:
    paginas = [
        "\n".join(
            (
                "VI. Programa analítico",
                "Semana    Tema             Evaluación    Contenido",
                "  1       Tema alfa        EV-A          Contenido alfa primera parte",
                "                                      Contenido alfa segunda parte",
                "  2       Tema beta        EV-B          Contenido beta",
                "VII. Evaluación",
            )
        )
    ]

    filas = _extraer_programa_analitico_pdf(paginas)

    assert filas == [
        {
            "semana": "1",
            "pagina": "1",
            "tema": "Tema alfa",
            "contenido": "Contenido alfa primera parte Contenido alfa segunda parte",
            "texto": (
                "Semana 1 | Tema alfa | Contenido alfa primera parte Contenido alfa segunda parte"
            ),
        },
        {
            "semana": "2",
            "pagina": "1",
            "tema": "Tema beta",
            "contenido": "Contenido beta",
            "texto": "Semana 2 | Tema beta | Contenido beta",
        },
    ]


def test_programa_pdf_reasigna_continuaciones_a_la_fila_que_las_continua() -> None:
    paginas = [
        "\n".join(
            (
                "VI. Programa analítico",
                "Semana    Tema                         Contenido",
                "  4       ETL                           Técnicas avanzadas: técnicas,",
                "                                        métodos. Revisión de herramienta ETL.",
                "  5       Almacenes de Datos            Importancia. Componentes.",
                " 13       Sistemas lineales             Método de Gauss. Aplicaciones.",
                "                                        Matriz tecnológica. La matriz inversa de",
                " 14       Matriz de Leontief            Leontief. Aplicaciones a la economía.",
                " 15       Evaluación final               Examen final",
                "                                        Cierre de la evaluación continua,",
                " 16       Retroalimentación              retroalimentación del aprendizaje.",
                "VII. Evaluación",
            )
        )
    ]

    filas = _extraer_programa_analitico_pdf(paginas)
    por_semana = {fila["semana"]: fila for fila in filas}

    assert por_semana["4"]["contenido"] == (
        "Técnicas avanzadas: técnicas, métodos. Revisión de herramienta ETL."
    )
    assert por_semana["5"]["contenido"] == "Importancia. Componentes."
    assert por_semana["13"]["contenido"] == "Método de Gauss. Aplicaciones."
    assert por_semana["14"]["contenido"] == (
        "Matriz tecnológica. La matriz inversa de Leontief. Aplicaciones a la economía."
    )
    assert por_semana["15"]["contenido"] == "Examen final"
    assert por_semana["16"]["contenido"] == (
        "Cierre de la evaluación continua, retroalimentación del aprendizaje."
    )


def test_pdf_cell_recomposes_intra_word_fragments_by_advance() -> None:
    fragmentos = [
        (0.0, 10.0, 10.0, 126.0, "Región factible. Problema"),
        (128.0, 10.0, 10.0, 5.0, "s"),
        (137.0, 10.0, 10.0, 10.0, "de"),
        (153.0, 10.0, 10.0, 56.0, "programación"),
        (0.0, 0.0, 10.0, 21.0, "Integrales sobre r"),
        (22.0, 0.0, 10.0, 45.0, "egiones r"),
        (68.0, 0.0, 10.0, 15.0, "ect"),
        (84.0, 0.0, 10.0, 5.0, "a"),
        (90.0, 0.0, 10.0, 20.0, "ngul"),
        (111.0, 0.0, 10.0, 15.0, "are"),
        (127.0, 0.0, 10.0, 5.0, "s"),
        (0.0, -10.0, 10.0, 136.0, "Método de eliminación de Ga"),
        (145.0, -10.0, 10.0, 90.0, "uss para resolver "),
        (0.0, -20.0, 10.0, 40.0, "Evaluaci"),
        (41.0, -20.0, 10.0, 10.0, "ón "),
    ]

    assert _texto_celda_pdf(fragmentos) == (
        "Región factible. Problemas de programación "
        "Integrales sobre regiones rectangulares "
        "Método de eliminación de Gauss para resolver Evaluación"
    )


def test_geometric_pdf_program_isolates_columns_and_row_boundaries() -> None:
    rectangulos = [
        (0.0, 100.0, 30.0, 110.0),
        (31.0, 100.0, 140.0, 110.0),
        (141.0, 100.0, 300.0, 110.0),
        (301.0, 100.0, 380.0, 110.0),
        (0.0, 60.0, 30.0, 90.0),
        (31.0, 60.0, 140.0, 90.0),
        (141.0, 60.0, 300.0, 90.0),
        (301.0, 60.0, 380.0, 90.0),
        (0.0, 20.0, 30.0, 50.0),
        (31.0, 20.0, 140.0, 50.0),
        (141.0, 20.0, 300.0, 50.0),
        (301.0, 20.0, 380.0, 50.0),
    ]
    fragmentos = [
        (2.0, 105.0, 10.0, 9.0, "Sem"),
        (12.0, 105.0, 10.0, 9.0, "ana"),
        (60.0, 105.0, 10.0, 20.0, "Tema"),
        (180.0, 105.0, 10.0, 45.0, "Contenido"),
        (320.0, 105.0, 10.0, 50.0, "Evaluación"),
        (5.0, 75.0, 10.0, 5.0, "1"),
        (40.0, 75.0, 10.0, 75.0, "Funciones reales"),
        (40.0, 65.0, 10.0, 72.0, "de varias variables"),
        (150.0, 75.0, 10.0, 126.0, "Región factible. Problema"),
        (278.0, 75.0, 10.0, 5.0, "s"),
        (287.0, 75.0, 10.0, 10.0, "de"),
        (150.0, 65.0, 10.0, 56.0, "programación lineal."),
        (320.0, 75.0, 10.0, 10.0, "EV-1"),
        (5.0, 35.0, 10.0, 5.0, "2"),
        (40.0, 35.0, 10.0, 50.0, "Integrales"),
        (40.0, 25.0, 10.0, 82.0, "dobles y aplicaciones"),
        (150.0, 35.0, 10.0, 98.0, "negocios. Integrales"),
        (150.0, 25.0, 10.0, 112.0, "sobre regiones rectangulares."),
        (320.0, 35.0, 10.0, 10.0, "EV-2"),
    ]

    filas = _extraer_programa_analitico_geometrico_pdf(
        ["VI. Programa analítico"], [(fragmentos, rectangulos)]
    )

    assert [(fila["tema"], fila["contenido"]) for fila in filas] == [
        (
            "Funciones reales de varias variables",
            "Región factible. Problemas de programación lineal.",
        ),
        (
            "Integrales dobles y aplicaciones",
            "negocios. Integrales sobre regiones rectangulares.",
        ),
    ]


def test_extraer_pdf_conecta_geometria_al_programa_analitico(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    layout = "\n".join(
        (
            "I. Información general",
            "Asignatura Matemática para los negocios",
            "VI. Programa analítico",
            "S e m a n a    T e m a    C o n t e n i d o",
            "1                F u n c i o n e s    R e g i ó n  f a c t i b l e",
            "2                I n t e g r a l e s  A p l i c a c i o n e s",
            "VII. Evaluación",
        )
    )
    rectangulos = [
        (0.0, 100.0, 30.0, 110.0),
        (31.0, 100.0, 140.0, 110.0),
        (141.0, 100.0, 300.0, 110.0),
        (0.0, 60.0, 30.0, 90.0),
        (31.0, 60.0, 140.0, 90.0),
        (141.0, 60.0, 300.0, 90.0),
        (0.0, 20.0, 30.0, 50.0),
        (31.0, 20.0, 140.0, 50.0),
        (141.0, 20.0, 300.0, 50.0),
    ]
    fragmentos = [
        (2.0, 105.0, 10.0, 20.0, "Semana"),
        (60.0, 105.0, 10.0, 20.0, "Tema"),
        (180.0, 105.0, 10.0, 45.0, "Contenido"),
        (5.0, 75.0, 10.0, 5.0, "1"),
        (40.0, 75.0, 10.0, 60.0, "Funciones"),
        (150.0, 75.0, 10.0, 90.0, "Región factible"),
        (5.0, 35.0, 10.0, 5.0, "2"),
        (40.0, 35.0, 10.0, 55.0, "Integrales"),
        (150.0, 35.0, 10.0, 75.0, "Aplicaciones"),
    ]

    class _PaginaFalsa:
        def extract_text(self, extraction_mode: str | None = None) -> str:
            return layout

    class _LectorFalso:
        pages = [_PaginaFalsa()]

    monkeypatch.setattr(limpieza, "PdfReader", lambda _ruta: _LectorFalso())
    monkeypatch.setattr(
        limpieza,
        "_geometria_pdf_pagina",
        lambda _pagina: (fragmentos, rectangulos),
    )
    fuente = tmp_path / "matematica.pdf"
    fuente.write_bytes(b"pdf-falso")

    registro = _extraer_pdf(fuente, fuente.name, "NEGOCIOS", "2026-1")
    datos = registro["datos"]

    assert isinstance(datos, dict)
    assert datos["programa_analitico_detalle"] == [
        {
            "semana": "1",
            "pagina": "1",
            "tema": "Funciones",
            "contenido": "Región factible",
            "texto": "Semana 1 | Funciones | Región factible",
        },
        {
            "semana": "2",
            "pagina": "1",
            "tema": "Integrales",
            "contenido": "Aplicaciones",
            "texto": "Semana 2 | Integrales | Aplicaciones",
        },
    ]


def test_competencias_pdf_reconstruye_columnas_partidas_sin_carrera() -> None:
    competencias = _competencias_pdf(
        "\n".join(
            (
                "Competencias genéricas",
                "   Pensamiento           Obtiene una visión global sobre una situación "
                "compleja a partir",
                "     sistémico           de la integración de sus componentes." + " " * 43 + "G1",
                "                                       Competencias específicas",
                "   Control de la         Evalúa la implementación de planes y             "
                "Carrera de           E4",
                "       gestión           procesos, mediante indicadores y técnicas de    "
                "Administración",
                "                          control de gestión, para promover la mejora",
                "                          continua de la organización.",
                "                          Diseña estrategias de marketing de",
                "       Gestión            productos y servicios orientadas a los             "
                "Carrera de",
                "    estratégica           clientes, para demostrar su profundo"
                + " " * 18
                + "Marketing            E1",
                "                          conocimiento del mercado.",
            )
        )
    )

    assert [(fila["orden"], fila["nombre"]) for fila in competencias] == [
        ("1", "Pensamiento sistémico"),
        ("2", "Control de la gestión"),
        ("3", "Gestión estratégica"),
    ]
    assert competencias[1]["descripcion"] == (
        "Evalúa la implementación de planes y procesos, mediante indicadores y técnicas de "
        "control de gestión, para promover la mejora continua de la organización."
    )
    assert competencias[0]["descripcion"].endswith("a partir de la integración de sus componentes.")
    assert "Carrera de" not in competencias[1]["nombre"]
    assert "Administración" not in competencias[1]["descripcion"]
    assert "Carrera de" in competencias[1]["texto_evidencia"]
    assert all("G1" not in fila["texto_evidencia"] for fila in competencias)
    assert all("E4" not in fila["texto_evidencia"] for fila in competencias)


@pytest.mark.parametrize(
    ("codigo_curso", "id_silabo", "id_curso"),
    [
        ("6384", "SIL_b33bb90738f5fbe9", "CUR_31a6549f9c475d94"),
        ("650072", "SIL_f2a3c07826612aa6", "CUR_4943170169bf625d"),
    ],
)
def test_ids_curriculares_versionan_silabo_por_periodo_y_estabilizan_curso(
    codigo_curso: str,
    id_silabo: str,
    id_curso: str,
) -> None:
    assert limpieza._ids_curriculares(
        "INGENIERIA_DE_SISTEMAS",
        "2026-1",
        "Nombre que no define la identidad",
        codigo_curso,
    ) == (id_silabo, id_curso)
