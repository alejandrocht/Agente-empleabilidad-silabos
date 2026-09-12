"""Extraccion estructural de documentos curriculares PDF."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from agente.normalizador.silabos.extraccion_curricular import (
    _ciclo_desde_ruta,
    _deduplicar_evidencias_herramientas,
    _ids_curriculares,
    _nombre_desde_archivo,
    _normalizar_modalidad,
    _normalizar_naturaleza,
    _sin_referencias_curriculares,
    _texto,
    _unir_metadata,
)
from agente.normalizador.silabos.programa_pdf import (
    _extraer_programa_analitico_pdf,
    _normalizar_linea_pdf,
)

_PATRON_CODIGO_CURRICULAR = r"(?<![A-Z0-9])(?:[GE]\d+|[GE]{2,4})(?![A-Z0-9])"
_ETIQUETAS_METADATA_PDF = re.compile(
    r"^\s*(?:"
    r"Asignatura|Tipo\s+de\s+asignatura|C[oó]digo|Nivel|Cr[eé]ditos|Coordinador|"
    r"Docentes?|[ÁA]rea|Modalidad|Naturaleza|Requisito(?:s)?|"
    r"Horas\s+de\s+(?:teor[ií]a|pr[aá]ctica)|"
    r"(?:[IVXLC]+|\d+)\.\s+"
    r")\b",
    re.IGNORECASE,
)
_GeometriaPdfPagina = Callable[
    [Any],
    tuple[
        list[tuple[float, float, float, float, str]],
        list[tuple[float, float, float, float]],
    ],
]


def _normalizar_pdf_para_matching(
    texto: str,
    *,
    conservar_layout: bool = False,
) -> str:
    """Normaliza solo la representacion usada por regex y parsers."""

    return "\n".join(
        _normalizar_linea_pdf(linea, conservar_layout=conservar_layout)
        for linea in str(texto or "").splitlines()
    )


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
    """Extrae una seccion conservando columnas solo cuando el parser las usa."""

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


def _campo_pdf_metadata(texto: str, etiqueta: str, *, continuacion: bool = False) -> str:
    """Extrae metadatos de I. Informacion general sin usar el LLM.

    Los PDFs reales suelen partir el valor del coordinador en varias lineas.
    Solo ese campo consume continuaciones; los demas paran en la linea siguiente
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
    """Reconstruye filas de competencias de una tabla PDF con layout."""

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
        descripcion = _sin_referencias_curriculares(
            " ".join(actual["descripcion"])
        )  # type: ignore[arg-type]
        fragmento = _sin_referencias_curriculares(
            "\n".join(actual["fragmento"])
        )  # type: ignore[arg-type]
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
    """Encuentra el borde estable de la columna de descripcion."""

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
    """Separa metodologia y recursos del punto V sin promocionar recursos."""

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
    """Obtiene el cuerpo de un subtitulo PDF, incluso con espaciado de layout."""

    patron_fin = rf"(?={fin})" if fin else r"\Z"
    coincidencia = re.search(rf"(?is){inicio}\s*(.*?){patron_fin}", texto)
    return _texto(coincidencia.group(1)) if coincidencia else ""


def _pdf_text_advance(text: str, font: object, size: float) -> float:
    """Estima el avance renderizado desde el ancho medio de la fuente."""

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
    """Recopila texto y rectangulos de una pagina PDF sin persistir datos."""

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
    """Construye el contexto I--VI para el LLM sin VII+ ni bibliografia."""

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
    """Reconoce E/G numericos y alfabeticos sin convertir palabras en codigos."""

    return list(
        dict.fromkeys(
            coincidencia.group(0).upper()
            for coincidencia in re.finditer(
                _PATRON_CODIGO_CURRICULAR,
                _texto(texto).upper(),
            )
        )
    )


def _evidencias_herramientas_pdf(
    programa: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Expone evidencia PDF de herramientas solo desde la tabla VI."""

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


def _extraer_pdf(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
    *,
    pdf_reader: Callable[[Path], Any] = PdfReader,
    geometria_pdf_pagina: _GeometriaPdfPagina = _geometria_pdf_pagina,
) -> dict[str, object]:
    lector = pdf_reader(ruta)
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
        geometria_paginas.append(geometria_pdf_pagina(pagina))

    texto_fuente = _sin_referencias_curriculares("\n\f\n".join(paginas_layout or paginas_plano))
    texto_layout = _normalizar_pdf_para_matching("\n".join(paginas_layout))
    texto_plano = _normalizar_pdf_para_matching("\n".join(paginas_plano))
    curso = _campo_pdf_metadata(texto_layout, r"Asignatura") or _nombre_desde_archivo(nombre)
    codigo_curso = _campo_pdf_metadata(texto_layout, r"C[oó]digo")
    nivel = _campo_pdf_metadata(texto_layout, r"Nivel")
    coordinador = _campo_pdf_metadata(texto_layout, r"Coordinador", continuacion=True)
    creditos = _campo_pdf_metadata(texto_layout, r"Cr[eé]ditos")
    tipo_curso = _normalizar_naturaleza(
        _campo_pdf_metadata(texto_layout, r"Tipo\s+de\s+asignatura")
    )
    modalidad = _normalizar_modalidad(
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
    id_silabo, id_curso = _ids_curriculares(carrera, periodo, nombre, codigo_curso)
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
            "modalidad": modalidad,
            "codigo_curso": codigo_curso,
            "sumilla": sumilla,
            "logro_general": logro_general,
            "logros_especificos": logros,
            "competencias_declaradas": competencias,
            "metodologias_ensenanza": metodologias,
            "recursos_aprendizaje": recursos,
            "programa_analitico": programa,
            "programa_analitico_detalle": programa_detalle,
            "herramientas_evidencia": _evidencias_herramientas_pdf(programa_detalle),
            "texto_relevante": texto_relevante,
            "texto_fuente": texto_fuente,
        },
    }
