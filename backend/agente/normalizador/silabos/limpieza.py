"""Limpieza y extracción estructural de DOCX/PDF curriculares."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from docx import Document
from pypdf import PdfReader

from agente.config.settings import (
    ConfiguracionNormalizadorCurricular,
)
from agente.normalizador.embeddings import (
    DEFAULT_EMBEDDING_LIMITS,
    EmbeddingProvider,
    crear_retriever_curricular_opt_in,
    normalizar_limites,
)
from agente.normalizador.empleabilidad.catalogo import (
    CatalogoCHH,
    cargar_catalogo,
    cargar_catalogo_carrera,
    clave_concepto,
)
from agente.normalizador.empleabilidad.entrada import normalizar_etiqueta
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import (
    ArchivoSilabo,
    Hallazgo,
    ProgresoLimpiezaLLM,
    ResultadoLimpiezaSilabos,
    ResultadoValidacionSilabos,
)
from agente.normalizador.silabos.analista_llm import analizar_registros_curriculares
from agente.normalizador.silabos.entrada import PATRON_PERIODO, normalizar_periodo
from agente.normalizador.silabos.programa_pdf import (
    _extraer_programa_analitico_geometrico_pdf,
    _extraer_programa_analitico_pdf,
    _extraer_programa_analitico_pdf_layout,
    _reparar_fronteras_programa,
    _texto_celda_pdf,
)
from agente.normalizador.silabos.salida import (
    ResultadoCatalogoCurricular,
    _catalogo_curricular,
    construir_salidas_curriculares,
)

__all__ = (
    "_texto_celda_pdf",
    "_extraer_programa_analitico_geometrico_pdf",
    "_extraer_programa_analitico_pdf",
    "_reparar_fronteras_programa",
    "_extraer_programa_analitico_pdf_layout",
)

_PATRON_CODIGO_CURRICULAR = r"(?<![A-Z0-9])(?:[GE]\d+|[GE]{2,4})(?![A-Z0-9])"
_PATRON_REFERENCIA_CURRICULAR = (
    r"(?<![A-Z0-9])(?:L\d+|[GE]\d+|[GE]{2,4})(?![A-Z0-9])"
)
_SECCIONES_HERRAMIENTAS = (
    "recursos de aprendizaje",
    "recursos tecnologicos",
    "recursos tecnológicos",
    "software",
    "herramientas digitales",
)


def _normalizar_modalidad(valor: object) -> str:
    """Reduce la modalidad declarada al único vocabulario permitido por curso.csv."""

    clave = normalizar_etiqueta(valor).replace("_", " ").upper()
    if "PRESENCIAL" in clave:
        return "Presencial"
    if "HIBRID" in clave:
        return "Híbrido"
    if "VIRTUAL" in clave:
        return "Virtual"
    return ""


def _carreras_confiables_para_embeddings(
    configuracion_curricular: ConfiguracionNormalizadorCurricular,
) -> frozenset[tuple[str, str]]:
    """Lee solo parejas ``carrera@periodo`` explícitamente habilitadas."""

    configuradas = configuracion_curricular.embedding_carreras
    parejas: set[tuple[str, str]] = set()
    for entrada in configuradas.split(","):
        carrera, separador, periodo = entrada.partition("@")
        carrera_normalizada = normalizar_etiqueta(carrera)
        periodo_normalizado = normalizar_periodo(periodo)
        if (
            separador
            and carrera_normalizada
            and PATRON_PERIODO.fullmatch(periodo_normalizado) is not None
        ):
            parejas.add((carrera_normalizada, periodo_normalizado))
    return frozenset(parejas)


def _embeddings_curriculares_habilitados(
    carrera: str,
    periodo: str,
    enabled: bool,
    configuracion_curricular: ConfiguracionNormalizadorCurricular,
) -> bool:
    """Requiere opt-in general y una pareja carrera-periodo confiable."""

    pareja = (normalizar_etiqueta(carrera), normalizar_periodo(periodo))
    return (
        enabled
        and PATRON_PERIODO.fullmatch(pareja[1]) is not None
        and pareja in _carreras_confiables_para_embeddings(configuracion_curricular)
    )


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _sin_referencias_curriculares(valor: object) -> str:
    """Remove display-only outcome and competency labels from exported text."""

    return _texto(re.sub(_PATRON_REFERENCIA_CURRICULAR, " ", str(valor or "")))


def _normalizar_linea_pdf(valor: object, *, conservar_layout: bool = False) -> str:
    """Normaliza Unicode sin destruir el texto fuente ni las columnas visuales."""

    texto = unicodedata.normalize("NFKC", str(valor or ""))
    texto = texto.replace("\u00a0", " ").replace("\u00ad", "")
    texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Cf")
    if conservar_layout:
        return texto.rstrip()
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_pdf_para_matching(
    texto: str,
    *,
    conservar_layout: bool = False,
) -> str:
    """Normaliza solo la representación usada por regex y parsers."""

    return "\n".join(
        _normalizar_linea_pdf(linea, conservar_layout=conservar_layout)
        for linea in str(texto or "").splitlines()
    )


def _clave(valor: object) -> str:
    return normalizar_etiqueta(valor).replace(" ", "_")


def _hash_id(prefijo: str, *partes: str) -> str:
    payload = "|".join(clave_concepto(parte) for parte in partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _ids_curriculares(
    carrera: str,
    periodo: str,
    nombre: str,
    codigo_curso: str,
) -> tuple[str, str]:
    """Construye IDs compatibles con el identificador padre de los CSV."""

    codigo = _texto(codigo_curso)
    if codigo:
        return _hash_id("SIL", codigo), _hash_id("CUR", codigo)
    return (
        _hash_id("SIL", carrera, periodo, nombre),
        _hash_id("CUR", carrera, periodo, nombre),
    )


def _hallazgo(
    codigo: str,
    severidad: str,
    mensaje: str,
    archivo: str,
    detalle: str | None = None,
) -> Hallazgo:
    return Hallazgo(
        codigo=codigo,
        severidad=severidad,  # type: ignore[arg-type]
        mensaje=mensaje,
        hoja=archivo,
        detalle=detalle,
    )


def _filas_tabla(tabla: Any) -> list[list[str]]:
    """Devuelve filas lógicas sin repetir proyecciones de celdas combinadas.

    ``python-docx`` proyecta el texto de la celda que inicia una combinación
    vertical sobre cada fila de continuación. Cuando toda la fila continúa una
    combinación, no representa un registro curricular adicional. También proyecta una celda
    horizontalmente combinada una vez por cada columna de la cuadrícula; esas repeticiones
    consecutivas deben representar una sola celda lógica.
    """

    filas: list[list[str]] = []
    for fila in tabla.rows:
        celdas_fisicas = fila._tr.tc_lst
        if celdas_fisicas and all(_es_continuacion_vertical(celda) for celda in celdas_fisicas):
            continue
        celdas_logicas: list[str] = []
        celda_anterior = None
        for celda in fila.cells:
            if celda._tc is celda_anterior:
                continue
            celdas_logicas.append(_texto(celda.text))
            celda_anterior = celda._tc
        filas.append(celdas_logicas)
    return filas


def _es_continuacion_vertical(celda: Any) -> bool:
    combinacion = celda.tcPr.vMerge
    return combinacion is not None and combinacion.val != "restart"


def _codigos(texto: str, aceptar_no_numericos: bool = True) -> list[str]:
    """Extrae códigos declarados, incluidos formatos curriculares no estándar."""

    valor = _texto(texto).upper()
    numericos = re.findall(r"(?<![A-Z0-9])[GE]\d+(?![A-Z0-9])", valor)
    if not aceptar_no_numericos:
        return list(dict.fromkeys(numericos))
    if numericos:
        palabras_cortas = re.findall(
            r"(?<![A-Z0-9])[A-Z]{2,4}(?![A-Z0-9])",
            valor,
        )
        if len(valor.split()) <= 4:
            return list(dict.fromkeys(numericos + palabras_cortas))
        return list(dict.fromkeys(numericos))

    # Algunas carreras usan referencias como ``EE``. Solo se aceptan códigos
    # alfabéticos cuando la celda es corta; así no se convierten palabras de una
    # descripción extensa en competencias.
    palabras = re.findall(r"(?<![A-Z0-9])[A-Z]{2,4}(?![A-Z0-9])", valor)
    if len(valor.split()) <= 4:
        return list(dict.fromkeys(palabras))
    return []


def _extraer_docx(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
) -> dict[str, object]:
    doc = Document(str(ruta))
    metadata: dict[str, str] = {}
    ultima_etiqueta = ""
    if doc.tables:
        for fila in doc.tables[0].rows:
            valores = [_texto(celda.text) for celda in fila.cells]
            if len(valores) >= 2 and valores[0]:
                ultima_etiqueta = _clave(valores[0])
                metadata[ultima_etiqueta] = _unir_metadata(
                    metadata.get(ultima_etiqueta, ""), valores[1]
                )
            elif len(valores) >= 2 and ultima_etiqueta and valores[1]:
                # Algunos formatos extienden el coordinador en una fila sin
                # etiqueta. Se conserva en orden en vez de descartar nombres.
                metadata[ultima_etiqueta] = _unir_metadata(
                    metadata.get(ultima_etiqueta, ""), valores[1]
                )

    sumilla = ""
    if len(doc.tables) > 1:
        candidato = _texto(
            " ".join(celda.text for fila in doc.tables[1].rows for celda in fila.cells)
        )
        if candidato and _clave(candidato) != "sumilla":
            sumilla = candidato
    logro_general = ""
    logros: list[dict[str, object]] = []
    competencias: list[dict[str, str]] = []
    programa: list[str] = []
    herramientas_evidencia: list[dict[str, str]] = []

    for tabla in doc.tables:
        filas = _filas_tabla(tabla)
        if not filas:
            continue
        encabezado = _clave(" ".join(filas[0]))
        if "competencias_genericas" in encabezado or "competencias_especificas" in encabezado:
            for valores in filas[1:]:
                if len(valores) < 3:
                    continue
                if _codigos(valores[-1]) and valores[0] and not re.fullmatch(
                    r"L\d+", valores[0], re.I
                ):
                    competencias.append(
                        {
                            "orden": str(len(competencias) + 1),
                            "nombre": _sin_referencias_curriculares(valores[0]).strip(" ."),
                            "descripcion": _sin_referencias_curriculares(valores[1]),
                            "texto_evidencia": _sin_referencias_curriculares(
                                " | ".join(valores[:2])
                            ),
                        }
                    )
        if "logro_de_aprendizaje_general" in encabezado:
            if len(filas) > 1 and filas[1]:
                logro_general = filas[1][0]
            for valores in filas[1:]:
                if len(valores) >= 3 and re.fullmatch(r"L\d+", valores[0], re.I):
                    logros.append(
                        {
                            "orden": str(len(logros) + 1),
                            "descripcion": _sin_referencias_curriculares(valores[1]),
                            "texto_evidencia": _sin_referencias_curriculares(valores[1]),
                        }
                    )
        if "semana" in encabezado and ("tema" in encabezado or "contenido" in encabezado):
            for valores in filas[1:]:
                if valores and re.fullmatch(r"(?:[1-9]|1[0-5])", valores[0]):
                    programa.append(" | ".join(valor for valor in valores[1:3] if valor))
        herramientas_evidencia.extend(_herramientas_desde_tabla(filas))

    herramientas_evidencia.extend(_herramientas_desde_parrafos(doc))

    if not sumilla:
        for tabla in doc.tables:
            filas = _filas_tabla(tabla)
            for indice, valores in enumerate(filas):
                if valores and _clave(valores[0]) == "sumilla" and indice + 1 < len(filas):
                    sumilla = filas[indice + 1][0]
                    break
            if sumilla:
                break

    curso = _primer_metadata(metadata, ("nombre_del_curso", "nombre_curso", "curso", "asignatura"))
    curso = curso or _nombre_desde_archivo(nombre)
    nivel = _primer_metadata(metadata, ("nivel", "ciclo"))
    ciclo = _ciclo_desde_ruta(nombre) or nivel
    texto_relevante = " ".join(
        parte
        for parte in (
            sumilla,
            logro_general,
            " ".join(str(logro["descripcion"]) for logro in logros),
            " ".join(programa),
        )
        if parte
    )
    texto_fuente = _sin_referencias_curriculares(
        " ".join(
            [parrafo.text for parrafo in doc.paragraphs]
            + [celda.text for tabla in doc.tables for fila in tabla.rows for celda in fila.cells]
        )
    )
    id_silabo, id_curso = _ids_curriculares(
        carrera,
        periodo,
        nombre,
        _primer_metadata(metadata, ("codigo_del_curso", "codigo", "cod_asignatura")),
    )
    return {
        "id_silabo": id_silabo,
        "id_curso": id_curso,
        "carrera": carrera,
        "periodo": periodo,
        "origen": {"archivo": nombre, "formato": "docx"},
        "datos": {
            "curso": curso,
            "ciclo": ciclo,
            "nombre_curso": curso,
            "coordinador": _primer_metadata(metadata, ("coordinador", "coordinador_del_curso")),
            "creditos": _primer_metadata(metadata, ("creditos", "creditos_academicos")),
            "nivel": nivel,
            "tipo_curso": _normalizar_modalidad(
                _primer_metadata(
                    metadata,
                    ("modalidad", "modalidad_de_estudios", "modalidad_de_ensenanza"),
                )
            ),
            "codigo_curso": _primer_metadata(
                metadata,
                ("codigo_del_curso", "codigo", "cod_asignatura"),
            ),
            "sumilla": sumilla,
            "logro_general": logro_general,
            "logros_especificos": logros,
            "competencias_declaradas": competencias,
            "programa_analitico": programa,
            "herramientas_evidencia": _deduplicar_evidencias_herramientas(herramientas_evidencia),
            "texto_relevante": texto_relevante,
            "texto_fuente": texto_fuente,
        },
    }


def _extraer_pdf(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
) -> dict[str, object]:
    lector = PdfReader(ruta)
    paginas_layout: list[str] = []
    paginas_plano: list[str] = []
    geometria_paginas = []
    for pagina in lector.pages:
        try:
            texto_layout = pagina.extract_text(extraction_mode="layout") or ""
        except (AttributeError, TypeError, ValueError):
            texto_layout = ""
        texto_plano = pagina.extract_text() or texto_layout
        paginas_layout.append(texto_layout or texto_plano)
        paginas_plano.append(texto_plano or texto_layout)
        geometria_paginas.append(_geometria_pdf_pagina(pagina))

    texto_fuente = _sin_referencias_curriculares("\n\f\n".join(paginas_layout or paginas_plano))
    texto_layout = _normalizar_pdf_para_matching("\n".join(paginas_layout))
    texto_plano = _normalizar_pdf_para_matching("\n".join(paginas_plano))
    curso = _campo_pdf_metadata(texto_layout, r"Asignatura") or _nombre_desde_archivo(nombre)
    codigo_curso = _campo_pdf_metadata(texto_layout, r"C[oó]digo")
    nivel = _campo_pdf_metadata(texto_layout, r"Nivel")
    coordinador = _campo_pdf_metadata(texto_layout, r"Coordinador", continuacion=True)
    creditos = _campo_pdf_metadata(texto_layout, r"Cr[eé]ditos")
    tipo_curso = _normalizar_modalidad(
        _campo_pdf_metadata(
            texto_layout,
            r"Modalidad(?:\s+de\s+(?:estudios|enseñanza))?",
        )
    )
    sumilla = _seccion_pdf(
        texto_layout,
        r"II\.\s*Sumilla",
        r"III\.\s*Competencias",
    )
    bloque_competencias = _seccion_pdf_raw(
        "\n".join(paginas_layout),
        r"III\.\s*Competencias",
        r"IV\.\s*Logros\s+de\s+aprendizaje",
        conservar_layout=True,
    )
    bloque_logros = _seccion_pdf_raw(
        texto_plano,
        r"IV\.\s*Logros\s+de\s+aprendizaje",
        r"V\.\s*Estrategia\s+de\s+enseñanza",
        conservar_layout=False,
    )
    bloque_v = _seccion_pdf_raw(
        "\n".join(paginas_layout),
        r"V\.\s*Estrategia\s+de\s+enseñanza",
        r"VI\.\s*Programa\s+analítico",
        conservar_layout=True,
    )
    competencias = _competencias_pdf(bloque_competencias)
    # Algunas versiones de pypdf devuelven una palabra por línea en la
    # extracción plana. Para IV la estructura relevante son L1..Ln, no las
    # columnas, así que se colapsa solo este bloque antes de parsearlo.
    bloque_logros = _texto(bloque_logros)
    logro_general = _logro_general_pdf(bloque_logros)
    logros = _logros_pdf(bloque_logros)
    metodologias, recursos = _punto_v_pdf(bloque_v)
    programa_detalle = _extraer_programa_analitico_pdf(
        paginas_layout or paginas_plano,
        geometria_paginas=geometria_paginas,
    )
    programa = [str(fila["texto"]) for fila in programa_detalle]
    texto_relevante = _texto_relevante_pdf(
        curso=curso,
        codigo_curso=codigo_curso,
        ciclo=_ciclo_pdf(texto_layout) or _ciclo_desde_ruta(nombre),
        sumilla=sumilla,
        competencias=competencias,
        logro_general=logro_general,
        logros=logros,
        metodologias=metodologias,
        recursos=recursos,
        programa=programa,
    )
    id_silabo, id_curso = _ids_curriculares(
        carrera,
        periodo,
        nombre,
        codigo_curso,
    )
    return {
        "id_silabo": id_silabo,
        "id_curso": id_curso,
        "carrera": carrera,
        "periodo": periodo,
        "origen": {"archivo": nombre, "formato": "pdf"},
        "datos": {
            "curso": curso,
            "ciclo": _ciclo_pdf(texto_layout) or _ciclo_desde_ruta(nombre),
            "nombre_curso": curso,
            "coordinador": coordinador,
            "creditos": creditos,
            "nivel": nivel,
            "tipo_curso": tipo_curso,
            "codigo_curso": codigo_curso,
            "sumilla": sumilla,
            "logro_general": logro_general,
            "logros_especificos": logros,
            "competencias_declaradas": competencias,
            "metodologias_ensenanza": metodologias,
            "recursos_aprendizaje": recursos,
            # ``programa_analitico`` sigue siendo una lista de strings para no
            # romper consumidores existentes. El detalle añade provenance sin
            # cambiar ese contrato legacy.
            "programa_analitico": programa,
            "programa_analitico_detalle": programa_detalle,
            # Los recursos del punto V describen el contexto de enseñanza, no
            # herramientas concretas. La evidencia de herramientas PDF se
            # limita deliberadamente a las filas trazables del punto VI.
            "herramientas_evidencia": _evidencias_herramientas_pdf(programa_detalle),
            "texto_relevante": texto_relevante,
            "texto_fuente": texto_fuente,
        },
    }


def _seccion_pdf(texto: str, inicio: str, fin: str) -> str:
    coincidencia = re.search(
        rf"(?is){inicio}\s*(.*?)(?={fin})",
        _normalizar_pdf_para_matching(texto),
    )
    return _texto(coincidencia.group(1)) if coincidencia else ""


def _seccion_pdf_raw(
    texto: str,
    inicio: str,
    fin: str,
    *,
    conservar_layout: bool,
) -> str:
    """Extrae una sección conservando columnas solo cuando el parser las usa."""

    normalizado = _normalizar_pdf_para_matching(
        texto,
        conservar_layout=conservar_layout,
    )
    coincidencia = re.search(
        rf"(?is){inicio}\s*(.*?)(?={fin})",
        normalizado,
    )
    return coincidencia.group(1).strip() if coincidencia else ""


def _campo_pdf(texto: str, etiqueta: str) -> str:
    lineas = _normalizar_pdf_para_matching(texto).splitlines()
    patron = re.compile(rf"^\s*{etiqueta}(?:\s*[:.-]\s*|\s+|$)(.*)$", re.IGNORECASE)
    for indice, linea in enumerate(lineas):
        coincidencia = patron.match(linea)
        if coincidencia:
            valor = _texto(coincidencia.group(1))
            if valor:
                return valor
            for siguiente in lineas[indice + 1 : indice + 3]:
                candidato = _texto(siguiente)
                if candidato and not re.match(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]+\s*[:.-]", candidato):
                    return candidato
    return ""


_ETIQUETAS_METADATA_PDF = re.compile(
    r"^\s*(?:"
    r"Asignatura|Tipo\s+de\s+asignatura|C[oó]digo|Nivel|Cr[eé]ditos|Coordinador|"
    r"Docentes?|[ÁA]rea|Modalidad|Naturaleza|Requisito(?:s)?|"
    r"Horas\s+de\s+(?:teor[ií]a|pr[aá]ctica)|"
    r"(?:[IVXLC]+|\d+)\.\s+"
    r")\b",
    re.IGNORECASE,
)


def _campo_pdf_metadata(texto: str, etiqueta: str, *, continuacion: bool = False) -> str:
    """Extrae metadatos de I. Información general sin usar el LLM.

    Los PDFs reales suelen partir el valor del coordinador en varias líneas.
    Solo ese campo consume continuaciones; los demás paran en la línea siguiente
    para no absorber la siguiente etiqueta curricular.
    """

    lineas = _normalizar_pdf_para_matching(texto).splitlines()
    patron = re.compile(rf"^\s*{etiqueta}(?:\s*[:.-]\s*|\s+|$)(.*)$", re.IGNORECASE)
    for indice, linea in enumerate(lineas):
        coincidencia = patron.match(linea)
        if coincidencia is None:
            continue
        valores = [_texto(coincidencia.group(1))]
        for siguiente in lineas[indice + 1 :]:
            candidato = _texto(siguiente)
            if (
                not candidato
                or _ETIQUETAS_METADATA_PDF.match(candidato)
                or re.match(r"^[IVXLC]+\.\s", candidato)
            ):
                break
            if not continuacion:
                if not valores[0]:
                    valores.append(candidato)
                break
            valores.append(candidato)
        return _unir_metadata(*valores)
    return ""


def _competencias_pdf(texto: str) -> list[dict[str, str]]:
    """Rebuild competency rows from a layout-preserving PDF table.

    PDF text extraction frequently interleaves table cells by visual line. This
    parser keeps the name and description bands separate, drops the optional
    degree-program band, and stores the original row fragment as evidence.
    """

    lineas = [linea.rstrip() for linea in texto.splitlines() if linea.strip()]
    posiciones_codigo = [
        coincidencia.start()
        for linea in lineas
        for coincidencia in re.finditer(_PATRON_CODIGO_CURRICULAR, linea, re.IGNORECASE)
    ]
    if not posiciones_codigo:
        return []

    columna_codigo = min(posiciones_codigo)
    columna_carrera = _columna_carrera_pdf(lineas, columna_codigo)
    columna_descripcion = _columna_descripcion_pdf(
        lineas,
        columna_codigo,
        columna_carrera,
    )
    if columna_descripcion is None:
        return _competencias_pdf_lineal(texto)

    resultado: list[dict[str, str]] = []
    actual: dict[str, object] | None = None

    def cerrar_actual() -> None:
        nonlocal actual
        if actual is None:
            return
        codigo = _texto(actual["codigo"])
        nombre = _sin_referencias_curriculares(" ".join(actual["nombre"]))  # type: ignore[arg-type]
        descripcion = _sin_referencias_curriculares(" ".join(actual["descripcion"]))  # type: ignore[arg-type]
        fragmento = _sin_referencias_curriculares("\n".join(actual["fragmento"]))  # type: ignore[arg-type]
        if codigo and nombre and descripcion:
            resultado.append(
                {
                    "orden": str(len(resultado) + 1),
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "texto_evidencia": fragmento,
                }
            )
        actual = None

    for linea in lineas:
        if re.match(r"^\s*Competencias\s+(?:gen[eé]ricas|espec[ií]ficas)\s*$", linea, re.I):
            continue
        tiene_carrera = bool(
            re.search(r"\bCarrera\s+de\b", linea, re.IGNORECASE)
            or (actual is not None and actual["tiene_carrera"])
        )
        nombre, descripcion, codigo = _separar_fila_competencia_pdf(
            linea,
            columna_descripcion,
            columna_carrera if tiene_carrera else None,
            columna_codigo,
        )
        if not (nombre or descripcion or codigo):
            continue

        if actual is None:
            actual = {
                "codigo": codigo,
                "nombre": [],
                "descripcion": [],
                "fragmento": [],
                "tiene_carrera": tiene_carrera,
            }
        elif codigo and _texto(actual["codigo"]):
            cerrar_actual()
            actual = {
                "codigo": codigo,
                "nombre": [],
                "descripcion": [],
                "fragmento": [],
                "tiene_carrera": tiene_carrera,
            }
        elif _inicia_siguiente_competencia_pdf(actual, nombre, descripcion):
            cerrar_actual()
            actual = {
                "codigo": codigo,
                "nombre": [],
                "descripcion": [],
                "fragmento": [],
                "tiene_carrera": tiene_carrera,
            }
        elif codigo:
            actual["codigo"] = codigo

        assert actual is not None
        if nombre:
            actual["nombre"].append(nombre)  # type: ignore[union-attr]
        if descripcion:
            actual["descripcion"].append(descripcion)  # type: ignore[union-attr]
        actual["fragmento"].append(linea)  # type: ignore[union-attr]
        actual["tiene_carrera"] = bool(actual["tiene_carrera"] or tiene_carrera)

    cerrar_actual()
    return resultado


def _columna_carrera_pdf(lineas: list[str], columna_codigo: int) -> int | None:
    posiciones = [
        coincidencia.start()
        for linea in lineas
        for coincidencia in re.finditer(r"\bCarrera\s+de\b", linea, re.IGNORECASE)
        if coincidencia.start() < columna_codigo
    ]
    return min(posiciones) if posiciones else None


def _columna_descripcion_pdf(
    lineas: list[str],
    columna_codigo: int,
    columna_carrera: int | None,
) -> int | None:
    """Find the stable left edge of the description column.

    A single PDF line can contain justified words separated by wide gaps. The
    true column boundary is the only left edge repeated across wrapped rows.
    """

    limite = columna_carrera if columna_carrera is not None else columna_codigo
    candidatos: list[int] = []
    for linea in lineas:
        if re.match(r"^\s*Competencias\s+", linea, re.IGNORECASE):
            continue
        for coincidencia in re.finditer(r"(?:^| {2,})(\S+)", linea):
            inicio = coincidencia.start(1)
            if 18 <= inicio < limite:
                candidatos.append(inicio)
    if len(candidatos) < 2:
        return None

    # Nearby coordinates represent the same rendered column despite PDF glyph
    # rounding. Prefer the densest cluster, then its leftmost stable boundary.
    mejor_inicio = 0
    mejor_soporte: tuple[int, int] = (0, 0)
    for candidato in sorted(set(candidatos)):
        grupo = [inicio for inicio in candidatos if abs(inicio - candidato) <= 2]
        soporte = (len(grupo), -min(grupo))
        if soporte > mejor_soporte:
            mejor_soporte = soporte
            mejor_inicio = min(grupo)
    return mejor_inicio if mejor_soporte[0] >= 2 else None


def _separar_fila_competencia_pdf(
    linea: str,
    columna_descripcion: int,
    columna_carrera: int | None,
    columna_codigo: int,
) -> tuple[str, str, str]:
    # Wrapped degree-program values can start a few glyph positions before the
    # ``Carrera de`` label, so reserve its left-side padding as well.
    limite_descripcion = (
        max(columna_descripcion, columna_carrera - 4)
        if columna_carrera is not None
        else columna_codigo
    )
    nombre = _texto(linea[:columna_descripcion])
    descripcion = _texto(linea[columna_descripcion:limite_descripcion])
    codigo = _texto(linea[columna_codigo:]).upper()
    codigos = _codigos_curriculares_pdf(codigo)
    return nombre, descripcion, codigos[0] if len(codigos) == 1 else ""


def _inicia_siguiente_competencia_pdf(
    actual: dict[str, object],
    nombre: str,
    descripcion: str,
) -> bool:
    if not _texto(actual["codigo"]) or not descripcion[:1].isupper():
        return False
    if nombre:
        return True
    descripcion_actual = _texto(" ".join(actual["descripcion"]))  # type: ignore[arg-type]
    return descripcion_actual.endswith((".", ";", ":"))


def _competencias_pdf_lineal(texto: str) -> list[dict[str, str]]:
    cuerpo = re.sub(r"(?i)^competencias\s+(?:genéricas|específicas)\s+", "", texto)
    coincidencias = list(re.finditer(_PATRON_CODIGO_CURRICULAR, cuerpo, flags=re.IGNORECASE))
    resultado: list[dict[str, str]] = []
    for indice, coincidencia in enumerate(coincidencias):
        inicio = coincidencias[indice - 1].end() if indice else 0
        segmento = _texto(cuerpo[inicio : coincidencia.start()])
        segmento = re.sub(r"(?i)^competencias\s+(?:genéricas|específicas)\s+", "", segmento)
        if not segmento:
            continue
        verbos = (
            "Analiza|Analizar|Aplica|Aplicar|Argumenta|Desarrolla|Desarrollar|"
            "Diseña|Diseñar|Evalúa|Evaluar|Gestiona|Gestionar|Interpreta|"
            "Interpretar|Planifica|Planificar|Propone|Proponer|Reconoce|"
            "Reconocer|Utiliza|Utilizar"
        )
        verbo = re.search(rf"\b(?:{verbos})\b", segmento, flags=re.IGNORECASE)
        if verbo:
            nombre = _sin_referencias_curriculares(segmento[: verbo.start()]).strip(" -")
            descripcion = _sin_referencias_curriculares(segmento[verbo.start() :])
        else:
            palabras = segmento.split()
            nombre = _sin_referencias_curriculares(" ".join(palabras[: min(6, len(palabras))]))
            descripcion = _sin_referencias_curriculares(segmento)
        if nombre and descripcion:
            resultado.append(
                {
                    "orden": str(len(resultado) + 1),
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "texto_evidencia": _sin_referencias_curriculares(segmento),
                }
            )
    return resultado


def _logro_general_pdf(texto: str) -> str:
    coincidencia = re.search(
        r"(?is)Logro de aprendizaje general\s+(.*?)(?=Logros de aprendizaje específicos)",
        texto,
    )
    return _texto(coincidencia.group(1)) if coincidencia else ""


def _logros_pdf(texto: str) -> list[dict[str, object]]:
    inicio = re.search(r"(?is)Logros de aprendizaje específicos\s+", texto)
    if inicio is None:
        return []
    cuerpo = texto[inicio.end() :]
    marcas = list(re.finditer(r"\bL\d+\b", cuerpo, flags=re.IGNORECASE))
    resultado: list[dict[str, object]] = []
    for indice, marca in enumerate(marcas):
        fin = marcas[indice + 1].start() if indice + 1 < len(marcas) else len(cuerpo)
        segmento = cuerpo[marca.end() : fin]
        descripcion = _sin_referencias_curriculares(segmento)
        if descripcion:
            resultado.append(
                {
                    "orden": str(len(resultado) + 1),
                    "descripcion": descripcion,
                    "texto_evidencia": descripcion,
                }
            )
    return resultado


def _punto_v_pdf(texto: str) -> tuple[str, str]:
    """Separa metodología y recursos del punto V sin promocionar recursos."""

    normalizado = _normalizar_pdf_para_matching(texto)
    metodologia = _subseccion_pdf(
        normalizado,
        r"Metodolog[ií]as\s+y\s+t[eé]cnicas\s+de\s+enseñanza",
        r"Recursos\s+de\s+aprendizaje",
    )
    recursos = _subseccion_pdf(
        normalizado,
        r"Recursos\s+de\s+aprendizaje",
        None,
    )
    return metodologia, recursos


def _subseccion_pdf(texto: str, inicio: str, fin: str | None) -> str:
    """Obtiene el cuerpo de un subtítulo PDF, incluso con espaciado de layout."""

    patron_fin = rf"(?={fin})" if fin else r"\Z"
    coincidencia = re.search(rf"(?is){inicio}\s*(.*?){patron_fin}", texto)
    return _texto(coincidencia.group(1)) if coincidencia else ""


def _pdf_text_advance(text: str, font: object, size: float) -> float:
    """Estimate the rendered advance using the embedded font's average width."""

    average_width = 500.0
    try:
        descendants = font["/DescendantFonts"]  # type: ignore[index]
        descriptor = descendants[0].get_object()["/FontDescriptor"].get_object()
        average_width = float(descriptor.get("/AvgWidth", average_width))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        pass
    return max(size * 0.2, len(text) * size * average_width / 1000)


def _geometria_pdf_pagina(
    pagina: Any,
) -> tuple[
    list[tuple[float, float, float, float, str]],
    list[tuple[float, float, float, float]],
]:
    """Collect text and cell rectangles from one PDF page without persisting data."""

    fragmentos: list[tuple[float, float, float, float, str]] = []
    rectangulos: list[tuple[float, float, float, float]] = []

    def transformar(x: float, y: float, matriz: object) -> tuple[float, float]:
        a, b, c, d, e, f = (float(valor) for valor in matriz)
        return (x * a + y * c + e, x * b + y * d + f)

    def visitante_texto(
        valor: object,
        matriz_usuario: object,
        matriz_texto: object,
        _fuente: object,
        tamano: object,
    ) -> None:
        original_text = str(valor or "").rstrip("\r\n")
        text = _normalizar_linea_pdf(original_text)
        if not text:
            return
        try:
            texto_matriz = tuple(float(valor) for valor in matriz_texto)
            x, y = transformar(texto_matriz[4], texto_matriz[5], matriz_usuario)
            source_advance = _pdf_text_advance(original_text or text, _fuente, float(tamano))
            end_x, _ = transformar(
                texto_matriz[4] + source_advance, texto_matriz[5], matriz_usuario
            )
            advance = abs(end_x - x) or source_advance
            fragmentos.append((x, y, float(tamano), advance, original_text or text))
        except (TypeError, ValueError):
            return

    def visitante_operador(
        operador: object,
        operandos: object,
        matriz_usuario: object,
        _matriz_texto: object,
    ) -> None:
        if operador != b"re":
            return
        try:
            x, y, ancho, alto = (float(valor) for valor in operandos)
            esquinas = (
                transformar(x, y, matriz_usuario),
                transformar(x + ancho, y, matriz_usuario),
                transformar(x, y + alto, matriz_usuario),
                transformar(x + ancho, y + alto, matriz_usuario),
            )
        except (TypeError, ValueError):
            return
        xs = [punto[0] for punto in esquinas]
        ys = [punto[1] for punto in esquinas]
        if max(xs) - min(xs) >= 20 and max(ys) - min(ys) >= 8:
            rectangulos.append((min(xs), min(ys), max(xs), max(ys)))

    try:
        pagina.extract_text(visitor_text=visitante_texto, visitor_operand_before=visitante_operador)
    except (AttributeError, TypeError, ValueError):
        return ([], [])
    return (fragmentos, rectangulos)



def _texto_relevante_pdf(
    *,
    curso: str,
    codigo_curso: str,
    ciclo: str,
    sumilla: str,
    competencias: list[dict[str, str]],
    logro_general: str,
    logros: list[dict[str, object]],
    metodologias: str,
    recursos: str,
    programa: list[str],
) -> str:
    """Construye el contexto I--VI para el LLM sin VII+ ni bibliografía."""

    competencias_texto = " ".join(
        _texto(f"{item.get('nombre', '')} {item.get('descripcion', '')}") for item in competencias
    )
    logros_texto = " ".join(_texto(item.get("descripcion")) for item in logros)
    programa_util = [
        fila
        for fila in programa
        if not re.search(r"(?i)\b(?:evaluaci[oó]n\s+final|retroalimentaci[oó]n)\b", fila)
    ]
    partes = (
        f"Curso: {curso}",
        f"Código: {codigo_curso}" if codigo_curso else "",
        f"Ciclo: {ciclo}" if ciclo else "",
        f"Sumilla: {sumilla}" if sumilla else "",
        f"Competencias: {competencias_texto}" if competencias_texto else "",
        f"Logro general: {logro_general}" if logro_general else "",
        f"Logros específicos: {logros_texto}" if logros_texto else "",
        f"Metodologías de enseñanza: {metodologias}" if metodologias else "",
        f"Recursos de aprendizaje: {recursos}" if recursos else "",
        f"Programa analítico: {' '.join(programa_util)}" if programa_util else "",
    )
    return _texto(" ".join(parte for parte in partes if parte))


def _codigos_curriculares_pdf(texto: str) -> list[str]:
    """Reconoce E/G numéricos y alfabéticos sin convertir palabras en códigos."""

    return list(
        dict.fromkeys(
            coincidencia.group(0).upper()
            for coincidencia in re.finditer(
                _PATRON_CODIGO_CURRICULAR,
                _texto(texto).upper(),
            )
        )
    )


def _seccion_herramientas(encabezado: str) -> str:
    normalizado = encabezado.replace("_", " ")
    return next(
        (seccion for seccion in _SECCIONES_HERRAMIENTAS if seccion == normalizado),
        "",
    )


def _herramientas_desde_tabla(filas: list[list[str]]) -> list[dict[str, str]]:
    """Toma solo la fila que sigue a un encabezado estructurado exacto."""

    resultado: list[dict[str, str]] = []
    for indice, fila in enumerate(filas[:-1]):
        seccion = _seccion_herramientas(_clave(" ".join(fila)))
        if not seccion:
            continue
        evidencia = _texto(" ".join(filas[indice + 1]))
        if evidencia:
            resultado.append({"seccion": seccion, "texto": evidencia})
    return resultado


def _herramientas_desde_parrafos(doc: Any) -> list[dict[str, str]]:
    """Extrae solo el contenido inmediatamente posterior a un encabezado confiable."""

    resultado: list[dict[str, str]] = []
    parrafos = [_texto(parrafo.text) for parrafo in doc.paragraphs]
    for indice, parrafo in enumerate(parrafos):
        seccion = _seccion_herramientas(_clave(parrafo))
        if not seccion:
            continue
        for candidato in parrafos[indice + 1 : indice + 3]:
            if not candidato or _seccion_herramientas(_clave(candidato)):
                break
            if re.match(r"^(?:[IVXLC]+|\d+)\s*[.)]", candidato, flags=re.IGNORECASE):
                break
            resultado.append({"seccion": seccion, "texto": candidato})
            break
    return resultado


def _evidencias_herramientas_pdf(
    programa: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Expone la evidencia PDF de herramientas solo desde la tabla VI.

    El analista aplica el catálogo y valida los nombres concretos más adelante.
    Aquí no se infiere software: se preserva la fila curricular que lo nombra,
    con semana y página para auditoría.
    """

    resultado: list[dict[str, str]] = []
    for fila in programa:
        texto = _texto(fila.get("texto"))
        if not texto:
            continue
        semana = _texto(fila.get("semana"))
        pagina = _texto(fila.get("pagina"))
        seccion = "Programa analítico"
        if semana:
            seccion += f" — semana {semana}"
        if pagina:
            seccion += f" (página {pagina})"
        resultado.append({"seccion": seccion, "texto": texto})
    return _deduplicar_evidencias_herramientas(resultado)


def _deduplicar_evidencias_herramientas(
    evidencias: list[dict[str, str]],
) -> list[dict[str, str]]:
    resultado: list[dict[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for evidencia in evidencias:
        seccion = _texto(evidencia.get("seccion"))
        texto = _texto(evidencia.get("texto"))
        clave = (seccion.lower(), texto.lower())
        if seccion and texto and clave not in vistos:
            vistos.add(clave)
            resultado.append({"seccion": seccion, "texto": texto})
    return resultado


def _ciclo_pdf(texto: str) -> str:
    niveles = {
        "primero": "01",
        "segundo": "02",
        "tercero": "03",
        "cuarto": "04",
        "quinto": "05",
        "sexto": "06",
        "séptimo": "07",
        "septimo": "07",
        "octavo": "08",
        "noveno": "09",
        "décimo": "10",
        "decimo": "10",
    }
    nivel = _campo_pdf(texto, r"Nivel").lower()
    return niveles.get(nivel, nivel)


def limpiar_archivo(
    ruta_entrada: Path,
    directorio_ejecucion: Path,
    validacion: ResultadoValidacionSilabos,
    catalogo: CatalogoCHH | None = None,
    usar_llm: bool = False,
    al_actualizar_progreso_llm: Callable[[ProgresoLimpiezaLLM], None] | None = None,
    progreso_inicial: ProgresoLimpiezaLLM | None = None,
    id_ejecucion: str = "",
    cancelada: Callable[[], bool] | None = None,
    embedding_enabled: bool | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    embedding_limits: Mapping[str, int] | None = None,
    embedding_pool: int | None = None,
    configuracion_curricular: ConfiguracionNormalizadorCurricular | None = None,
) -> ResultadoLimpiezaSilabos:
    """Materializa la fuente y construye el paquete curricular CSV.

    La entrada de producción del normalizador curricular activa ``usar_llm``;
    el parámetro explícito se conserva para pruebas offline y seams controlados.
    Cuando está activo, el LLM decide la normalización semántica por lotes y
    Python conserva la evidencia, IDs, esquema y relaciones.
    """

    fuentes = directorio_ejecucion / "fuentes_curriculares"
    limpios = directorio_ejecucion / "limpios"
    reportes = directorio_ejecucion / "salidas" / "reportes"
    fuentes.mkdir(parents=True, exist_ok=True)
    limpios.mkdir(parents=True, exist_ok=True)
    reportes.mkdir(parents=True, exist_ok=True)
    cuarentena: list[dict[str, object]] = []
    hallazgos: list[Hallazgo] = []
    registros: list[dict[str, object]] = []
    if usar_llm and configuracion_curricular is None:
        raise ValueError("La limpieza curricular con LLM requiere configuracion_curricular")
    progreso_extraccion = progreso_inicial or ProgresoLimpiezaLLM(
        fase="preparando",
        chunks_completados=0,
        chunks_totales=0,
        logros_procesados=0,
        logros_totales=0,
        silabos_procesados=0,
        silabos_totales=len(validacion.archivos),
        decisiones_cacheadas=0,
        reintentos=0,
        silabos_detectados=0,
        mensaje="Preparando la extracción de sílabos.",
    ).con_evento("Preparando la extracción de sílabos.")

    def publicar_progreso(progreso: ProgresoLimpiezaLLM) -> None:
        nonlocal progreso_extraccion
        progreso_extraccion = progreso
        if al_actualizar_progreso_llm is not None:
            al_actualizar_progreso_llm(progreso)

    def verificar_cancelacion() -> None:
        if cancelada is not None and cancelada():
            raise CancelacionSolicitada()

    if embedding_limits is not None:
        normalizar_limites(embedding_limits, defaults=DEFAULT_EMBEDDING_LIMITS)

    if usar_llm and progreso_inicial is None:
        publicar_progreso(progreso_extraccion)

    verificar_cancelacion()
    materializados = _materializar(ruta_entrada, fuentes, validacion.archivos, cancelada)
    for indice_archivo, archivo in enumerate(validacion.archivos, start=1):
        verificar_cancelacion()
        ruta = materializados[archivo.nombre]
        logros_archivo = 0
        silabo_extraido = False
        try:
            if archivo.formato == "docx":
                registro = _extraer_docx(
                    ruta,
                    archivo.nombre,
                    validacion.carrera,
                    validacion.periodo,
                )
            else:
                registro = _extraer_pdf(
                    ruta,
                    archivo.nombre,
                    validacion.carrera,
                    validacion.periodo,
                )
            datos = registro["datos"]
            if isinstance(datos, dict) and not datos.get("texto_relevante"):
                hallazgo = _hallazgo(
                    "SILABO_SIN_TEXTO_RELEVANTE",
                    "warning",
                    "El archivo no produjo texto curricular utilizable.",
                    archivo.nombre,
                )
                hallazgos.append(hallazgo)
                cuarentena.append(
                    {
                        "id_silabo": registro["id_silabo"],
                        "origen": registro["origen"],
                        "codigo": hallazgo.codigo,
                        "mensaje": hallazgo.mensaje,
                    }
                )
            registros.append(registro)
            silabo_extraido = True
            if isinstance(datos, dict):
                logros_archivo = len(datos.get("logros_especificos", []))
        except Exception as exc:
            hallazgo = _hallazgo(
                "SILABO_ILEGIBLE",
                "error",
                "No se pudo extraer la estructura del sílabo.",
                archivo.nombre,
                f"{type(exc).__name__}: {str(exc)[:200]}",
            )
            hallazgos.append(hallazgo)
            cuarentena.append(
                {
                    "id_archivo": archivo.nombre,
                    "codigo": hallazgo.codigo,
                    "mensaje": hallazgo.mensaje,
                    "detalle": hallazgo.detalle,
                }
            )
        if usar_llm:
            logros_detectados = 0
            for registro_extraido in registros:
                datos_extraidos = registro_extraido.get("datos")
                if not isinstance(datos_extraidos, dict):
                    continue
                logros_extraidos = datos_extraidos.get("logros_especificos", [])
                if isinstance(logros_extraidos, list):
                    logros_detectados += len(logros_extraidos)
            silabos_detectados = len(
                {
                    str(registro.get("id_silabo") or "")
                    for registro in registros
                    if registro.get("id_silabo")
                }
            )
            progreso_extraccion = replace(
                progreso_extraccion,
                fase="extrayendo",
                logros_detectados=logros_detectados,
                logros_totales=logros_detectados,
                silabos_detectados=silabos_detectados,
                silabos_procesados=0,
                silabos_totales=len(validacion.archivos),
            ).con_evento(
                f"Logros detectados: {logros_detectados}. Sílabos detectados: "
                f"{silabos_detectados}/{len(validacion.archivos)}.",
                logros_chunk=logros_archivo,
                silabos_chunk=1 if silabo_extraido else 0,
            )
            publicar_progreso(progreso_extraccion)

    staging = limpios / "silabos.jsonl"
    verificar_cancelacion()
    with staging.open("w", encoding="utf-8", newline="\n") as salida_staging:
        for registro in registros:
            salida_staging.write(
                json.dumps(registro, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
    try:
        catalogo_base = catalogo or cargar_catalogo()
        # Un catálogo inyectado representa el contexto completo de la
        # ejecución (pruebas o ejecución controlada), por lo que no debe
        # mezclarse silenciosamente con un perfil instalado en disco.
        catalogo_carrera = (
            None
            if catalogo is not None
            else cargar_catalogo_carrera(
                validacion.carrera,
                validacion.periodo,
            )
        )
        propuestas_llm = {}
        analisis_llm = None
        if usar_llm:
            try:
                verificar_cancelacion()
                catalogo_para_llm = _catalogo_curricular(
                    registros,
                    catalogo_base,
                    catalogo_carrera,
                )
                embeddings_habilitados = _embeddings_curriculares_habilitados(
                    validacion.carrera,
                    validacion.periodo,
                    configuracion_curricular.embeddings_habilitados
                    if embedding_enabled is None
                    else embedding_enabled,
                    configuracion_curricular,
                )
                # El catálogo para el LLM puede mezclar vocabulario global y
                # curricular. El índice semántico solo acepta la capa específica
                # de carrera/ciclo; sin ella, se conserva el fallback léxico.
                retriever_embedding = (
                    crear_retriever_curricular_opt_in(
                        catalogo_carrera,
                        career=validacion.carrera,
                        period=validacion.periodo,
                        enabled=embeddings_habilitados,
                        provider=embedding_provider,
                        configuracion_curricular=configuracion_curricular,
                    )
                    if catalogo_carrera is not None
                    else None
                )
                analisis_llm = analizar_registros_curriculares(
                    registros,
                    catalogo_para_llm,
                    validacion.carrera,
                    validacion.periodo,
                    directorio_ejecucion,
                    al_actualizar_progreso=publicar_progreso,
                    progreso_inicial=progreso_extraccion,
                    id_ejecucion=id_ejecucion,
                    cancelada=cancelada,
                    embedding_retriever=retriever_embedding,
                    limites_candidatos=embedding_limits,
                    pool_retrieval=embedding_pool,
                    configuracion_curricular=configuracion_curricular,
                )
                propuestas_llm = analisis_llm.propuestas
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                hallazgos.append(
                    _hallazgo(
                        "ANALISTA_LLM_NO_DISPONIBLE",
                        "warning",
                        (
                            "El analista curricular no estuvo disponible; se conserva "
                            "el resultado determinista."
                        ),
                        validacion.archivo,
                        f"{type(exc).__name__}: {str(exc)[:200]}",
                    )
                )
                _escribir_json(
                    reportes / "analisis_llm.json",
                    {
                        "estado": "FALLBACK_DETERMINISTA",
                        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                        "propuestas_pendientes": 0,
                    },
                )
                publicar_progreso(
                    replace(
                        progreso_extraccion,
                        fase="error",
                        reporte_final="disponible",
                    ).con_evento(
                        "El análisis LLM no estuvo disponible; continúa la salida determinista."
                    )
                )
        resultado_catalogo = construir_salidas_curriculares(
            registros,
            validacion,
            directorio_ejecucion,
            catalogo_base,
            catalogo_carrera,
            propuestas_llm,
        )
        if analisis_llm is not None:
            _escribir_jsonl(reportes / "decisiones_llm.jsonl", analisis_llm.reportes)
            _escribir_json(
                reportes / "analisis_llm.json",
                {
                    "estado": "COMPLETADO",
                    "modelo_analista": analisis_llm.modelo_analista,
                    "modelo_analista_residual": analisis_llm.modelo_analista_residual,
                    "lotes": analisis_llm.lotes,
                    "propuestas_pendientes": len(analisis_llm.propuestas),
                    "decisiones_escaladas": analisis_llm.decisiones_escaladas,
                    "decisiones_reportadas": len(analisis_llm.reportes),
                    "auditoria_contexto": analisis_llm.auditoria_contexto,
                },
            )
            if usar_llm:
                publicar_progreso(
                    replace(
                        progreso_extraccion,
                        fase="completado",
                        reporte_final="disponible",
                    ).con_evento("Reporte LLM disponible.")
                )
            report_outputs = tuple(
                resultado_catalogo.outputs
                + (
                    _output(
                        reportes / "decisiones_llm.jsonl",
                        "auditoria_llm",
                        len(analisis_llm.reportes),
                    ),
                    _output(reportes / "analisis_llm.json", "auditoria_llm", 1),
                )
            )
            resultado_catalogo = replace(resultado_catalogo, outputs=report_outputs)
    except CancelacionSolicitada:
        _escribir_jsonl(
            reportes / "decisiones_llm.jsonl",
            (
                {
                    "tipo": "sistema",
                    "estado": "CANCELADO",
                    "detalle": "El análisis se detuvo antes del siguiente lote LLM.",
                },
            ),
        )
        _escribir_json(
            reportes / "analisis_llm.json",
            {
                "estado": "CANCELADO",
                "propuestas_pendientes": 0,
                "mensaje": "La ejecución fue cancelada antes de completar el análisis.",
            },
        )
        _escribir_jsonl(reportes / "cuarentena.jsonl", tuple(cuarentena))
        if usar_llm:
            publicar_progreso(
                replace(
                    progreso_extraccion,
                    fase="cancelado",
                    reporte_final="cancelado",
                ).con_evento("El análisis LLM fue cancelado por el usuario.")
            )
        raise
    except Exception as exc:
        if usar_llm:
            publicar_progreso(
                replace(
                    progreso_extraccion,
                    fase="error",
                    reporte_final="error",
                ).con_evento(
                    "No se pudo completar el reporte LLM; se conservan los avances previos."
                )
            )
        hallazgo = _hallazgo(
            "CATALOGO_CURRICULAR_NO_DISPONIBLE",
            "error",
            "No se pudo construir el catálogo curricular con los catálogos base.",
            validacion.archivo,
            f"{type(exc).__name__}: {str(exc)[:200]}",
        )
        hallazgos.append(hallazgo)
        resultado_catalogo = ResultadoCatalogoCurricular(
            publicable=False,
            relaciones=0,
            competencias=0,
            habilidades=0,
            herramientas=0,
            outputs=(),
            hallazgos=(),
            cuarentena=(),
        )

    cuarentena.extend(resultado_catalogo.cuarentena)
    cuarentena_path = reportes / "cuarentena.jsonl"
    with cuarentena_path.open("w", encoding="utf-8", newline="\n") as salida_cuarentena:
        for fila in cuarentena:
            salida_cuarentena.write(
                json.dumps(fila, ensure_ascii=False, separators=(",", ":")) + "\n"
            )

    hallazgos_totales = tuple(hallazgos) + resultado_catalogo.hallazgos
    return ResultadoLimpiezaSilabos(
        registros=len(registros),
        outputs=resultado_catalogo.outputs,
        hallazgos=hallazgos_totales,
        publicable=resultado_catalogo.publicable,
        relaciones=resultado_catalogo.relaciones,
        competencias=resultado_catalogo.competencias,
        habilidades=resultado_catalogo.habilidades,
        herramientas=resultado_catalogo.herramientas,
        pendientes=resultado_catalogo.pendientes,
        release_gate=resultado_catalogo.release_gate,
    )


def _materializar(
    ruta_entrada: Path,
    directorio: Path,
    archivos: tuple[ArchivoSilabo, ...],
    cancelada: Callable[[], bool] | None = None,
) -> dict[str, Path]:
    def verificar_cancelacion() -> None:
        if cancelada is not None and cancelada():
            raise CancelacionSolicitada()

    resultado: dict[str, Path] = {}
    if ruta_entrada.suffix.lower() != ".zip":
        verificar_cancelacion()
        nombre = archivos[0].nombre
        destino = directorio / Path(nombre).name
        shutil.copyfile(ruta_entrada, destino)
        resultado[nombre] = destino
        return resultado
    with zipfile.ZipFile(ruta_entrada) as paquete:
        for archivo in archivos:
            verificar_cancelacion()
            destino = directorio / archivo.nombre
            destino.parent.mkdir(parents=True, exist_ok=True)
            with (
                paquete.open(archivo.nombre.replace("\\", "/")) as origen,
                destino.open("wb") as salida,
            ):
                shutil.copyfileobj(origen, salida)
            resultado[archivo.nombre] = destino
    return resultado


def _primer_metadata(metadata: dict[str, str], claves: tuple[str, ...]) -> str:
    for clave in claves:
        if metadata.get(clave):
            return metadata[clave]
    return ""


def _unir_metadata(*valores: str) -> str:
    """Conserva valores declarados en un orden estable dentro de una celda CSV."""

    resultado: list[str] = []
    vistos: set[str] = set()
    for valor in valores:
        texto = _texto(valor)
        clave = texto.casefold()
        if texto and clave not in vistos:
            vistos.add(clave)
            resultado.append(texto)
    return " | ".join(resultado)


def _nombre_desde_archivo(nombre: str) -> str:
    base = Path(nombre).stem.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", base).strip().title()


def _ciclo_desde_ruta(nombre: str) -> str:
    coincidencia = re.search(r"ciclo[_ -]?(\d+)", nombre, re.IGNORECASE)
    return coincidencia.group(1) if coincidencia else ""


def _escribir_json(ruta: Path, contenido: dict[str, object]) -> None:
    ruta.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _escribir_jsonl(ruta: Path, filas: tuple[dict[str, object], ...]) -> None:
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")))
            archivo.write("\n")


def _output(ruta: Path, tipo: str, registros: int) -> dict[str, object]:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    ejecucion = next(
        (padre for padre in ruta.parents if padre.name.startswith("NOR_")),
        None,
    )
    return {
        "tipo": tipo,
        "archivo": str(ruta.relative_to(ejecucion)) if ejecucion else ruta.name,
        "registros": registros,
        "bytes": ruta.stat().st_size,
        "sha256": digest.hexdigest(),
    }
