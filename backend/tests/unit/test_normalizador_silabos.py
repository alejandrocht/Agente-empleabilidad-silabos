"""Pruebas del contrato y staging curricular."""

from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from docx import Document

from agente.config import settings
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import ProgresoLimpiezaLLM
from agente.normalizador.silabos import limpieza
from agente.normalizador.silabos.analista_llm import ResultadoAnalisisCurricular
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
from agente.normalizador.silabos.salida import (
    CURSOS_SCHEMA,
    _competencias_declaradas_por_texto,
    _id_carrera,
    _resolver_habilidad_canonica,
)


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
    documento.save(ruta)


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
    documento.save(ruta)


def _crear_docx_codigo_no_declarado(ruta: Path, incluir_competencia: bool = True) -> None:
    documento = Document()
    metadata = documento.add_table(rows=1, cols=2)
    metadata.cell(0, 0).text = "Curso"
    metadata.cell(0, 1).text = "Introducción a las finanzas"
    sumilla = documento.add_table(rows=2, cols=1)
    sumilla.cell(0, 0).text = "Sumilla"
    sumilla.cell(1, 0).text = "Fundamentos de evaluación de indicadores financieros."
    if incluir_competencia:
        competencia = documento.add_table(rows=2, cols=3)
        competencia.cell(0, 0).text = "Competencias específicas"
        competencia.cell(0, 1).text = "Descripción"
        competencia.cell(0, 2).text = "Código"
        competencia.cell(1, 0).text = "Evaluación financiera"
        competencia.cell(1, 1).text = "Evaluar argumentos y evidencia para sustentar decisiones."
        competencia.cell(1, 2).text = "G7"
    logro = documento.add_table(rows=2, cols=3)
    logro.cell(0, 0).text = "Logro de aprendizaje general"
    logro.cell(0, 1).text = "Descripción"
    logro.cell(0, 2).text = "Competencias"
    logro.cell(1, 0).text = "L2"
    logro.cell(
        1, 1
    ).text = "Evaluar indicadores financieros para sustentar decisiones de inversión."
    logro.cell(1, 2).text = "E2"
    documento.save(ruta)


def _crear_docx_codigo_alfabetico_con_herramientas(ruta: Path) -> None:
    documento = Document()
    metadata = documento.add_table(rows=1, cols=2)
    metadata.cell(0, 0).text = "Curso"
    metadata.cell(0, 1).text = "Herramientas para marketing"
    sumilla = documento.add_table(rows=2, cols=1)
    sumilla.cell(0, 0).text = "Sumilla"
    sumilla.cell(1, 0).text = "Gestión estratégica de productos y clientes."
    competencia = documento.add_table(rows=2, cols=3)
    competencia.cell(0, 0).text = "Competencias específicas"
    competencia.cell(0, 1).text = "Descripción"
    competencia.cell(0, 2).text = "Código"
    competencia.cell(1, 0).text = "Gestión estratégica"
    competencia.cell(1, 1).text = "Diseñar estrategias de marketing."
    competencia.cell(1, 2).text = "E1"
    logro = documento.add_table(rows=2, cols=3)
    logro.cell(0, 0).text = "Logro de aprendizaje general"
    logro.cell(0, 1).text = "Descripción"
    logro.cell(0, 2).text = "Competencias"
    logro.cell(1, 0).text = "L1"
    logro.cell(1, 1).text = "Diseñar una estrategia de marketing para un producto."
    logro.cell(1, 2).text = "EE"
    recursos = documento.add_table(rows=2, cols=1)
    recursos.cell(0, 0).text = "Recursos de aprendizaje"
    recursos.cell(1, 0).text = "MS Excel, MS Word y MS Project."
    documento.save(ruta)


def _crear_docx_con_bibliografia_que_parece_herramienta(ruta: Path) -> None:
    _crear_docx_codigo_alfabetico_con_herramientas(ruta)
    documento = Document(ruta)
    recursos = documento.tables[-1]
    recursos.cell(1, 0).text = "Microsoft Excel para analizar datos."
    documento.add_paragraph("Bibliografía")
    documento.add_paragraph(
        "https://ejemplo.edu/index.php; Box-Jenkins; Valor Presente Neto (VPN); "
        "Brijs, Bert; Slack, N."
    )
    documento.save(ruta)


def _catalogo_financiero() -> CatalogoCHH:
    return CatalogoCHH(
        competencias=(
            ConceptoCHH(
                "COMP_FIN",
                "Evaluación financiera",
                "Evaluar indicadores financieros para sustentar decisiones.",
                "dura",
            ),
        ),
        habilidades=(
            ConceptoCHH(
                "HAB_FIN",
                "Evaluar indicadores financieros para sustentar decisiones de inversión",
                "Evaluar indicadores financieros para sustentar decisiones de inversión.",
            ),
        ),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def _catalogo_con_habilidad_bases_de_datos() -> CatalogoCHH:
    return CatalogoCHH(
        competencias=(),
        habilidades=(
            ConceptoCHH(
                "HAB_DB",
                "Modelar bases de datos relacionales",
                "Modelar bases de datos relacionales.",
            ),
        ),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def test_valida_y_limpia_docx_con_carrera_y_periodo(tmp_path: Path) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")

    assert validacion.valida is True
    assert validacion.carrera == "INGENIERIA_DE_SISTEMAS"
    assert validacion.archivos[0].formato == "docx"

    ejecucion = tmp_path / "ejecucion"
    resultado = limpiar_archivo(
        fuente,
        ejecucion,
        validacion,
        _catalogo_con_habilidad_bases_de_datos(),
    )
    assert resultado.registros == 1
    assert resultado.publicable is True
    assert resultado.relaciones == 1
    registro = json.loads((ejecucion / "limpios" / "silabos.jsonl").read_text(encoding="utf-8"))
    assert registro["datos"]["curso"] == "Diseño de bases de datos"
    assert registro["datos"]["logros_especificos"][0] == {
        "orden": "1",
        "descripcion": "Modelar bases de datos relacionales",
        "texto_evidencia": "Modelar bases de datos relacionales",
    }
    assert {output["archivo"] for output in resultado.outputs} == {
        "salidas/curso.csv",
        "salidas/catalogo_competencias.csv",
        "salidas/catalogo_habilidades.csv",
        "salidas/catalogo_herramientas.csv",
        "salidas/cobertura_curricular.csv",
        "salidas/competencias_fuente.jsonl",
        "salidas/habilidades_fuente.jsonl",
        "salidas/herramientas_fuente.jsonl",
        "salidas/cobertura_curricular_fuente.jsonl",
        "salidas/cobertura_curricular_canonica.jsonl",
        "salidas/pendientes_curriculares.jsonl",
        "salidas/release_gate.json",
    }
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
        "catalogo_competencias.csv": [
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve_competencia",
            "tipo_competencia",
        ],
        "catalogo_habilidades.csv": [
            "id_habilidad",
            "nombre_habilidad",
            "descripcion_breve",
        ],
        "catalogo_herramientas.csv": [
            "id_herramienta",
            "nombre_herramienta",
            "descripcion_breve_herramienta",
        ],
        "cobertura_curricular.csv": [
            "id_cob_curricular",
            "id_curso",
            "id_silabo",
            "id_competencia",
            "id_habilidad",
            "id_herramienta",
        ],
    }
    for nombre, esperado in schemas.items():
        with (ejecucion / "salidas" / nombre).open(encoding="utf-8-sig", newline="") as archivo:
            assert next(csv.reader(archivo)) == esperado
        assert (ejecucion / "salidas" / "reportes" / "habilidades_fuente.jsonl").is_file()


def test_orden_de_archivos_no_depende_del_empaquetado_del_zip(tmp_path: Path) -> None:
    """El orden interno de `infolist()` no debe filtrarse al resultado.

    El mismo contenido reempaquetado en otro orden producía lotes distintos y,
    con ellos, otra respuesta del LLM. El orden normalizado lo fija.
    """

    nombres = [
        "2026-2 SIL ZOOLOGÍA.docx",
        "2026-2 SIL ÁLGEBRA.docx",
        "2026-2 SIL CÁLCULO II.docx",
    ]
    observados: list[list[str]] = []
    for etiqueta, orden in (("ascendente", nombres), ("descendente", list(reversed(nombres)))):
        paquete = tmp_path / f"{etiqueta}.zip"
        with zipfile.ZipFile(paquete, "w") as archivo:
            for nombre in orden:
                archivo.writestr(nombre, b"contenido")
        validacion = validar_archivo(paquete, "Ingeniería de Sistemas", "2026-2")
        observados.append([item.nombre for item in validacion.archivos])

    esperado = [
        "2026-2 SIL ÁLGEBRA.docx",
        "2026-2 SIL CÁLCULO II.docx",
        "2026-2 SIL ZOOLOGÍA.docx",
    ]
    assert observados[0] == esperado
    assert observados[1] == esperado
    assert observados[0] == observados[1]


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
    documento.save(fuente)

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
        "tipo_curso": "Obligatorio",
    }
    assert datos["modalidad"] == "Híbrido"


def test_tipo_curso_publica_la_naturaleza_declarada_de_la_asignatura(tmp_path: Path) -> None:
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
    documento.save(fuente)

    datos = _extraer_docx(fuente, fuente.name, "PRUEBA", "2031-2")["datos"]

    assert isinstance(datos, dict)
    assert datos["tipo_curso"] == "Electivo"
    assert datos["modalidad"] == ""


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
    documento.save(fuente)

    datos = _extraer_docx(fuente, fuente.name, "PRUEBA", "2031-2")["datos"]

    assert isinstance(datos, dict)
    assert datos["programa_analitico"] == [
        "Tema normal | Contenido normal",
        "Tema combinado | Contenido combinado",
    ]


def test_publica_logros_detectados_durante_la_extraccion(monkeypatch, tmp_path: Path) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    progresos = []
    monkeypatch.setattr(
        limpieza,
        "analizar_registros_curriculares",
        lambda *_args, **_kwargs: ResultadoAnalisisCurricular(
            reportes=(),
            modelo_analista="llm-test",
            lotes=1,
        ),
    )

    limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        _catalogo_con_habilidad_bases_de_datos(),
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


def test_preserva_el_ultimo_chunk_si_el_analista_falla_tarde(monkeypatch, tmp_path: Path) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")
    progresos = []

    def analizar_con_fallo(*_args, **kwargs):
        actualizar = kwargs["al_actualizar_progreso"]
        progreso = ProgresoLimpiezaLLM(
            fase="analista",
            chunks_completados=1,
            chunks_totales=2,
            logros_procesados=8,
            logros_totales=16,
            silabos_procesados=1,
            silabos_totales=76,
            decisiones_cacheadas=8,
            reintentos=0,
            silabos_detectados=76,
        ).con_evento("Chunk 1/2 de Analista LLM completado.")
        actualizar(progreso)
        actualizar(
            replace(
                progreso,
                chunks_completados=2,
                logros_procesados=16,
                silabos_procesados=3,
            ).con_evento("Chunk 2/2 de Analista LLM completado.")
        )
        raise RuntimeError("fallo tardío simulado")

    monkeypatch.setattr(limpieza, "analizar_registros_curriculares", analizar_con_fallo)

    limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        _catalogo_con_habilidad_bases_de_datos(),
        usar_llm=True,
        configuracion_curricular=settings.configuracion_normalizador_curricular(),
        al_actualizar_progreso_llm=progresos.append,
    )

    progreso_final = progresos[-1]
    assert progreso_final.fase == "error"
    assert progreso_final.silabos_detectados == 76
    assert progreso_final.silabos_procesados == 3
    assert any("Chunk 1/2" in evento.mensaje for evento in progreso_final.eventos)
    assert any("Chunk 2/2" in evento.mensaje for evento in progreso_final.eventos)
    assert progreso_final.eventos[-1].mensaje.startswith("El análisis LLM no estuvo disponible")


def test_cancelacion_conserva_reportes_auditables_llm(monkeypatch, tmp_path: Path) -> None:
    fuente = tmp_path / "Ciclo_03" / "DISENO_DE_BASES_DE_DATOS.docx"
    fuente.parent.mkdir()
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Ingeniería de Sistemas", "2030-1")

    monkeypatch.setattr(
        limpieza,
        "analizar_registros_curriculares",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CancelacionSolicitada()),
    )

    ejecucion = tmp_path / "ejecucion"
    try:
        limpiar_archivo(
            fuente,
            ejecucion,
            validacion,
            _catalogo_con_habilidad_bases_de_datos(),
            usar_llm=True,
            configuracion_curricular=settings.configuracion_normalizador_curricular(),
        )
    except CancelacionSolicitada:
        pass
    else:
        raise AssertionError("La cancelación debe propagarse al gestor de ejecuciones.")

    reportes = ejecucion / "salidas" / "reportes"
    assert (reportes / "decisiones_llm.jsonl").is_file()
    assert (reportes / "cuarentena.jsonl").is_file()
    analisis = json.loads((reportes / "analisis_llm.json").read_text(encoding="utf-8"))
    assert analisis["estado"] == "CANCELADO"


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
        "texto_evidencia": "Desarrollar el texto completo y verificable del logro .",
    }


def test_publica_auditoria_contexto_en_resumen_llm(monkeypatch, tmp_path: Path) -> None:
    fuente = tmp_path / "DISENO_DE_BASES_DE_DATOS.docx"
    _crear_docx(fuente)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    auditoria = {
        "version_contexto": "contexto-curricular/v1",
        "version_catalogo": "catalogo-test",
        "hash_contextos": "hash-test",
    }
    analisis = ResultadoAnalisisCurricular(
        reportes=(),
        modelo_analista="llm-test",
        lotes=1,
        auditoria_contexto=auditoria,
    )
    monkeypatch.setattr(
        limpieza,
        "analizar_registros_curriculares",
        lambda *_args, **_kwargs: analisis,
    )

    limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        _catalogo_con_habilidad_bases_de_datos(),
        usar_llm=True,
        configuracion_curricular=settings.configuracion_normalizador_curricular(),
    )

    resumen = json.loads(
        (tmp_path / "ejecucion" / "salidas" / "reportes" / "analisis_llm.json").read_text(
            encoding="utf-8"
        )
    )
    assert resumen["auditoria_contexto"] == auditoria


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


def test_resuelve_logro_por_evidencia_textual_sin_referencia_de_tabla(tmp_path: Path) -> None:
    fuente = tmp_path / "INTRODUCCION_A_LAS_FINANZAS.docx"
    _crear_docx_codigo_no_declarado(fuente)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")

    resultado = limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        _catalogo_financiero(),
    )

    assert resultado.publicable is True
    assert resultado.relaciones == 1
    assert not any(hallazgo.severidad == "error" for hallazgo in resultado.hallazgos)
    competencias_fuente = [
        json.loads(line)
        for line in (tmp_path / "ejecucion" / "salidas" / "reportes" / "competencias_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        fila["estado_resolucion"] == "DECLARADA"
        and fila["metodo_vinculacion_logro"] == "COINCIDENCIA_TEXTUAL_DECLARADA"
        for fila in competencias_fuente
    )


def test_conserva_referencia_de_fuente_sin_catalogo_o_declaracion(tmp_path: Path) -> None:
    fuente = tmp_path / "CURSO_FINANCIERO.docx"
    _crear_docx_codigo_no_declarado(fuente, incluir_competencia=False)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    catalogo_vacio = CatalogoCHH((), (), (), {}, ("test",), "test")

    resultado = limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        catalogo_vacio,
    )

    assert resultado.publicable is False
    assert resultado.relaciones == 0
    assert any(
        hallazgo.codigo == "CURSO_SIN_COMPETENCIA_DECLARADA" for hallazgo in resultado.hallazgos
    )
    assert not any(
        (tmp_path / "ejecucion" / "salidas" / nombre).exists()
        for nombre, _ in (
            ("catalogo_competencias.csv", ()),
            ("catalogo_habilidades.csv", ()),
            ("catalogo_herramientas.csv", ()),
            ("cobertura_curricular.csv", ()),
        )
    )
    habilidades_fuente = (
        (tmp_path / "ejecucion" / "salidas" / "reportes" / "habilidades_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(habilidades_fuente) == 1
    cobertura_fuente = (
        (tmp_path / "ejecucion" / "salidas" / "reportes" / "cobertura_curricular_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert cobertura_fuente == []


def test_no_materializa_catalogos_mientras_queda_habilidad_pendiente(tmp_path: Path) -> None:
    fuente = tmp_path / "CURSO_FINANCIERO.docx"
    _crear_docx_codigo_no_declarado(fuente, incluir_competencia=False)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    catalogo_vacio = CatalogoCHH((), (), (), {}, ("test",), "test")

    resultado = limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        catalogo_vacio,
    )

    assert resultado.release_gate["decision"] == "BLOCK_IMPORT"
    assert "UNRESOLVED_CURRICULAR_RECORDS" in resultado.release_gate["blockers"]
    assert not (tmp_path / "ejecucion" / "salidas" / "catalogo_habilidades.csv").exists()


def test_no_publica_habilidad_canonica_sin_cadena_de_competencia(tmp_path: Path) -> None:
    fuente = tmp_path / "CURSO_FINANCIERO.docx"
    _crear_docx_codigo_no_declarado(fuente, incluir_competencia=False)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    catalogo_solo_habilidad = CatalogoCHH(
        competencias=(),
        habilidades=(
            ConceptoCHH(
                "HAB_FIN",
                "Evaluar indicadores financieros para sustentar decisiones de inversión",
                "Evaluar indicadores financieros para sustentar decisiones de inversión.",
            ),
        ),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )

    resultado = limpiar_archivo(
        fuente,
        tmp_path / "ejecucion",
        validacion,
        catalogo_solo_habilidad,
    )

    pendientes = (
        (tmp_path / "ejecucion" / "salidas" / "reportes" / "pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(pendientes) == 1
    assert json.loads(pendientes[0])["motivo"] == "HABILIDAD_SIN_COMPETENCIA_CANONICA"
    assert resultado.release_gate["checks"]["pending_preserved"]["ok"] is True


def test_prioriza_perfil_del_silabo_sin_exponer_referencias_alfabeticas(tmp_path: Path) -> None:
    fuente = tmp_path / "MATEMATICA_PARA_LA_GESTION.docx"
    _crear_docx_codigo_alfabetico_con_herramientas(fuente)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    catalogo = CatalogoCHH(
        competencias=(
            ConceptoCHH(
                "COMP_SISTEMAS",
                "Álgebra lineal aplicada",
                "Resolver matrices y sistemas.",
                "dura",
            ),
        ),
        habilidades=(),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )

    resultado = limpiar_archivo(fuente, tmp_path / "ejecucion", validacion, catalogo)

    assert resultado.publicable is True
    assert resultado.competencias == 1
    registro = json.loads(
        (tmp_path / "ejecucion" / "limpios" / "silabos.jsonl").read_text(encoding="utf-8")
    )
    assert registro["datos"]["logros_especificos"][0] == {
        "orden": "1",
        "descripcion": "Diseñar una estrategia de marketing para un producto.",
        "texto_evidencia": "Diseñar una estrategia de marketing para un producto.",
    }
    assert not any(
        (tmp_path / "ejecucion" / "salidas" / nombre).exists()
        for nombre in (
            "catalogo_competencias.csv",
            "catalogo_habilidades.csv",
            "catalogo_herramientas.csv",
            "cobertura_curricular.csv",
        )
    )
    candidatos = json.loads(
        (
            tmp_path / "ejecucion" / "salidas" / "reportes" / "candidatos_curriculares.json"
        ).read_text(encoding="utf-8")
    )
    assert candidatos["materialized"] is False
    fuente = (
        (tmp_path / "ejecucion" / "salidas" / "reportes" / "competencias_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert all("codigo_competencia" not in json.loads(line) for line in fuente)
    assert all("E1" not in json.dumps(json.loads(line)) for line in fuente)


def test_extrae_herramientas_de_recurso_estructurado_y_acepta_alias_ms(tmp_path: Path) -> None:
    fuente = tmp_path / "HERRAMIENTAS_MARKETING.docx"
    _crear_docx_codigo_alfabetico_con_herramientas(fuente)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    catalogo = CatalogoCHH(
        competencias=(),
        habilidades=(),
        herramientas=(
            ConceptoCHH("EXCEL", "Microsoft Excel", "Hoja de cálculo"),
            ConceptoCHH("WORD", "Microsoft Word", "Procesador de texto"),
            ConceptoCHH("PROJECT", "Microsoft Project", "Gestión de proyectos"),
        ),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )

    resultado = limpiar_archivo(fuente, tmp_path / "ejecucion", validacion, catalogo)

    assert resultado.publicable is True
    assert resultado.herramientas == 0
    assert not (tmp_path / "ejecucion" / "salidas" / "catalogo_herramientas.csv").exists()
    herramientas_fuente = [
        json.loads(line)
        for line in (tmp_path / "ejecucion" / "salidas" / "reportes" / "herramientas_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {fila["seccion_fuente"] for fila in herramientas_fuente} == {"recursos de aprendizaje"}
    assert {fila["nombre_herramienta"] for fila in herramientas_fuente} == {
        "Microsoft Excel",
        "Microsoft Project",
        "Microsoft Word",
    }
    assert all("MS " in fila["texto_evidencia"] for fila in herramientas_fuente)


def test_no_publica_herramientas_encontradas_solo_en_bibliografia(tmp_path: Path) -> None:
    fuente = tmp_path / "BIBLIOGRAFIA_MARKETING.docx"
    _crear_docx_con_bibliografia_que_parece_herramienta(fuente)
    validacion = validar_archivo(fuente, "Marketing", "2026-1")
    catalogo = CatalogoCHH(
        competencias=(),
        habilidades=(),
        herramientas=(
            ConceptoCHH("EXCEL", "Microsoft Excel", "Hoja de cálculo"),
            ConceptoCHH("PHP", "PHP", "Lenguaje"),
            ConceptoCHH("JENKINS", "Jenkins", "Automatización"),
            ConceptoCHH("VPN", "VPN", "Red privada virtual"),
            ConceptoCHH("BERT", "BERT", "Modelo"),
            ConceptoCHH("SLACK", "Slack", "Colaboración"),
        ),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )

    resultado = limpiar_archivo(fuente, tmp_path / "ejecucion", validacion, catalogo)

    assert resultado.publicable is True
    assert resultado.herramientas == 0
    assert not (tmp_path / "ejecucion" / "salidas" / "catalogo_herramientas.csv").exists()
    herramientas_fuente = [
        json.loads(line)
        for line in (tmp_path / "ejecucion" / "salidas" / "reportes" / "herramientas_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [fila["nombre_herramienta"] for fila in herramientas_fuente] == ["Microsoft Excel"]


def test_resuelve_habilidad_por_descripcion_y_rechaza_empate() -> None:
    descripcion = "Analizar comportamiento de consumidores mediante métricas de mercado."
    catalogo = CatalogoCHH(
        competencias=(),
        habilidades=(
            ConceptoCHH(
                "HAB_OK",
                "Gestión de información comercial",
                descripcion,
            ),
        ),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )

    resolucion = _resolver_habilidad_canonica(catalogo, descripcion)

    assert resolucion.concepto is not None
    assert resolucion.concepto.id == "HAB_OK"
    assert resolucion.metodo == "COINCIDENCIA_DESCRIPCION"
    assert resolucion.puntaje == 1.0

    ambigua = CatalogoCHH(
        competencias=(),
        habilidades=(
            ConceptoCHH("HAB_A", "Análisis comercial", descripcion),
            ConceptoCHH("HAB_B", "Investigación de mercado", descripcion),
        ),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )
    resolucion_ambigua = _resolver_habilidad_canonica(ambigua, descripcion)
    assert resolucion_ambigua.concepto is None
    assert resolucion_ambigua.metodo == "AMBIGUA_O_INSUFICIENTE"


def test_fallback_competencia_exige_margen_entre_candidatas() -> None:
    declaraciones = [
        {
            "codigo": "E1",
            "nombre": "Gestión estratégica",
            "descripcion": "Analizar datos de mercado para decisiones.",
        },
        {
            "codigo": "E2",
            "nombre": "Pensamiento crítico",
            "descripcion": "Analizar datos de mercado para decisiones.",
        },
    ]

    assert (
        _competencias_declaradas_por_texto(
            declaraciones,
            {"curso": "Marketing", "texto_relevante": ""},
            "Analizar datos de mercado para decisiones.",
        )
        == []
    )


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


def test_contrato_curso_y_mapeo_carrera_permanece_cerrado() -> None:
    assert CURSOS_SCHEMA == (
        "id_curso",
        "nombre_curso",
        "coordinador",
        "creditos",
        "nivel",
        "tipo_curso",
        "codigo_curso",
        "id_carrera",
    )
    assert _id_carrera("SISTEMAS") == "CAR_01375f53651cff38"
    assert _id_carrera("Carrera inexistente") == ""


def test_parser_pdf_uses_references_only_to_split_rows() -> None:
    competencias = _competencias_pdf(
        "Competencias específicas Gestión estratégica Diseñar estrategias de marketing EE"
    )
    logros = _logros_pdf(
        "Logros de aprendizaje específicos L1 Diseñar una estrategia de marketing EE"
    )

    assert competencias[0]["orden"] == "1"
    assert "codigo" not in competencias[0]
    assert competencias[0]["texto_evidencia"] == (
        "Gestión estratégica Diseñar estrategias de marketing"
    )
    assert logros == [
        {
            "orden": "1",
            "descripcion": "Diseñar una estrategia de marketing",
            "texto_evidencia": "Diseñar una estrategia de marketing",
        }
    ]


def test_extrae_pdf_layout_i_vi_y_conserva_vii_viii_solo_en_fuente(
    monkeypatch, tmp_path: Path
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
        def extract_text(self, extraction_mode=None):
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
    assert datos["tipo_curso"] == "Obligatorio"
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
    evidencias = datos["herramientas_evidencia"]
    assert all(item["seccion"].startswith("Programa analítico") for item in evidencias)
    assert not any("herramientas de ETL" in item["texto"] for item in evidencias)
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


def test_extraer_pdf_conecta_geometria_al_programa_analitico(monkeypatch, tmp_path: Path) -> None:
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
        def extract_text(self, extraction_mode=None):
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
                "     sistémico           de la integración de sus componentes."
                + " " * 43
                + "G1",
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
        ("6384", "SIL_31a6549f9c475d94", "CUR_31a6549f9c475d94"),
        ("650072", "SIL_4943170169bf625d", "CUR_4943170169bf625d"),
    ],
)
def test_ids_curriculares_usan_codigo_como_identidad_padre(
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
