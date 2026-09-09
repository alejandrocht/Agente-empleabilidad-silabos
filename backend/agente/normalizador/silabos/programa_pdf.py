"""Parser for the table in section VI of curricular PDF documents."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

_PATRON_SEMANA_PDF = re.compile(r"^\s*(\d{1,3})(?:\s+|$)")


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _normalizar_linea_pdf(valor: object, *, conservar_layout: bool = False) -> str:
    texto = unicodedata.normalize("NFKC", str(valor or ""))
    texto = texto.replace("\u00a0", " ").replace("\u00ad", "")
    texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Cf")
    if conservar_layout:
        return texto.rstrip()
    return re.sub(r"\s+", " ", texto).strip()


def _texto_celda_pdf(fragmentos: list[tuple[float, float, float, float, str]]) -> str:
    """Rebuild a cell in visual order, preserving letters split by the PDF."""

    lineas: dict[float, list[tuple[float, float, float, str]]] = {}
    for x, y, tamano, avance, texto in fragmentos:
        texto_normalizado = _normalizar_linea_pdf(texto)
        if texto_normalizado:
            lineas.setdefault(round(y, 1), []).append(
                (x, tamano, avance, texto_normalizado + (" " if texto[-1:].isspace() else ""))
            )
    texto_lineas: list[str] = []
    for fragmentos_linea in (lineas[posicion] for posicion in sorted(lineas, reverse=True)):
        piezas: list[str] = []
        ultimo_fin: float | None = None
        ultimo_x: float | None = None
        fragmentos_ordenados = sorted(fragmentos_linea)
        usa_avance = any(" " in texto.strip() for _, _, _, texto in fragmentos_ordenados)
        for x, tamano, avance, texto in fragmentos_ordenados:
            tiene_espacio_final = texto.endswith(" ")
            texto = texto.rstrip()
            separacion_avance = x - ultimo_fin if ultimo_fin is not None else float("inf")
            separacion_inicio = x - ultimo_x if ultimo_x is not None else float("inf")
            primera_palabra = texto.split(maxsplit=1)[0] if texto else ""
            continua_fragmento = (
                usa_avance
                and len(primera_palabra) > 2
                and primera_palabra[:1].islower()
                and " " in texto
                and separacion_avance <= tamano
            )
            cierra_fragmento = tiene_espacio_final and separacion_avance <= max(1.0, tamano * 0.3)
            unir = (
                piezas
                and not piezas[-1].endswith(" ")
                and (
                    usa_avance
                    and (separacion_avance <= max(1.0, tamano * 0.3) or continua_fragmento)
                    or not usa_avance
                    and (separacion_inicio <= max(1.0, tamano * 0.45) or cierra_fragmento)
                )
            )
            if unir:
                piezas[-1] += texto
            else:
                piezas.append(texto)
            if tiene_espacio_final:
                piezas[-1] += " "
            ultimo_fin = x + avance
            ultimo_x = x
        texto_lineas.append(" ".join(piezas))
    return _texto(" ".join(texto_lineas))


def _extraer_programa_analitico_geometrico_pdf(
    paginas: list[str],
    geometria_paginas: list[
        tuple[list[tuple[float, float, float, float, str]], list[tuple[float, float, float, float]]]
    ],
) -> list[dict[str, str]]:
    """Read table VI from its drawn cells instead of pypdf's text-stream order."""

    filas: list[dict[str, str]] = []
    semanas_vistas: set[str] = set()
    dentro_programa = False
    columnas_programa: tuple[
        tuple[float, float, float, float],
        tuple[float, float, float, float],
        tuple[float, float, float, float],
    ] | None = None
    for pagina_numero, (pagina, geometria) in enumerate(zip(paginas, geometria_paginas), start=1):
        if re.search(r"^\s*VI\.\s*Programa\s+anal[ií]tico\b", pagina, re.IGNORECASE | re.MULTILINE):
            dentro_programa = True
        if not dentro_programa:
            continue

        fragmentos, rectangulos = geometria

        def texto_rectangulo(rectangulo: tuple[float, float, float, float]) -> str:
            min_x, min_y, max_x, max_y = rectangulo
            return _texto_celda_pdf(
                [
                    fragmento
                    for fragmento in fragmentos
                    if min_x <= fragmento[0] <= max_x and min_y <= fragmento[1] <= max_y
                ]
            )

        celdas = [
            {"rectangulo": rectangulo, "texto": texto_rectangulo(rectangulo)}
            for rectangulo in rectangulos
        ]
        encabezado_semana = next(
            (
                celda
                for celda in celdas
                if re.sub(r"\s+", "", celda["texto"]).casefold() == "semana"
            ),
            None,
        )
        tiene_encabezado_programa = False
        if encabezado_semana is not None:
            rectangulo_semana = encabezado_semana["rectangulo"]
            centro_encabezado = (rectangulo_semana[1] + rectangulo_semana[3]) / 2

            def encabezado_columna(nombre: str) -> tuple[float, float, float, float] | None:
                for celda in celdas:
                    rectangulo = celda["rectangulo"]
                    centro = (rectangulo[1] + rectangulo[3]) / 2
                    if (
                        celda["texto"].casefold() == nombre
                        and rectangulo[0] > rectangulo_semana[0]
                        and abs(centro - centro_encabezado) < 5
                    ):
                        return rectangulo
                return None

            rectangulo_tema = encabezado_columna("tema")
            rectangulo_contenido = encabezado_columna("contenido")
            if rectangulo_tema is not None and rectangulo_contenido is not None:
                columnas_programa = (rectangulo_semana, rectangulo_tema, rectangulo_contenido)
                tiene_encabezado_programa = True
        if columnas_programa is None:
            continue

        rectangulo_semana, rectangulo_tema, rectangulo_contenido = columnas_programa

        def celda_fila(
            columna: tuple[float, float, float, float], centro_semana: float
        ) -> dict[str, object] | None:
            candidatas = [
                celda
                for celda in celdas
                if abs(celda["rectangulo"][0] - columna[0]) < 5
                and celda["rectangulo"][1] <= centro_semana <= celda["rectangulo"][3]
            ]
            return max(
                candidatas,
                key=lambda celda: celda["rectangulo"][3] - celda["rectangulo"][1],
                default=None,
            )

        semanas = sorted(
            (
                celda
                for celda in celdas
                if re.fullmatch(r"\d{1,3}", celda["texto"])
                and abs(celda["rectangulo"][0] - rectangulo_semana[0]) < 5
                and (
                    not tiene_encabezado_programa
                    or (celda["rectangulo"][1] + celda["rectangulo"][3]) / 2 < centro_encabezado
                )
            ),
            key=lambda celda: celda["rectangulo"][3],
            reverse=True,
        )
        for celda_semana in semanas:
            semana = str(celda_semana["texto"])
            if semana in semanas_vistas:
                continue
            rectangulo = celda_semana["rectangulo"]
            centro_semana = (rectangulo[1] + rectangulo[3]) / 2
            celda_tema = celda_fila(rectangulo_tema, centro_semana)
            celda_contenido = celda_fila(rectangulo_contenido, centro_semana)
            tema = _texto(celda_tema["texto"] if celda_tema else "")
            contenido = _texto(celda_contenido["texto"] if celda_contenido else "")
            if not tema and not contenido:
                continue
            partes = [parte for parte in (tema, contenido) if parte]
            filas.append(
                {
                    "semana": semana,
                    "pagina": str(pagina_numero),
                    "tema": tema,
                    "contenido": contenido,
                    "texto": f"Semana {semana} | {' | '.join(partes)}",
                }
            )
            semanas_vistas.add(semana)

        if re.search(r"^\s*VII\.\s*", pagina, re.IGNORECASE | re.MULTILINE):
            dentro_programa = False
    for indice, fila in enumerate(filas[:-1]):
        siguiente = filas[indice + 1]
        tema_siguiente = str(siguiente["tema"])
        continuacion_tema = re.match(r"^([a-záéíóúñ]+)\s+(.+)$", tema_siguiente)
        if continuacion_tema:
            fila["tema"] = _texto(f"{fila['tema']} {continuacion_tema.group(1)}")
            siguiente["tema"] = continuacion_tema.group(2)

        contenido = str(fila["contenido"])
        continuacion_contenido = re.match(r"^(.+?[.!?])(?:\s+|$)", str(siguiente["contenido"]))
        if continuacion_contenido and re.search(
            r"\b(?:y|o|de|del|la|el|para|en)\s*$", contenido, re.IGNORECASE
        ):
            texto = continuacion_contenido.group(1)
            fila["contenido"] = _texto(f"{contenido} {texto}")
            siguiente["contenido"] = _texto(str(siguiente["contenido"])[len(texto) :])

    for fila in filas:
        partes = [parte for parte in (fila["tema"], fila["contenido"]) if parte]
        fila["texto"] = f"Semana {fila['semana']} | {' | '.join(partes)}"
    return filas


def _extraer_programa_analitico_pdf(
    paginas: list[str],
    *,
    geometria_paginas: list[
        tuple[list[tuple[float, float, float, float, str]], list[tuple[float, float, float, float]]]
    ]
    | None = None,
) -> list[dict[str, str]]:
    """Prefer drawn-cell geometry; retain a layout fallback for non-tabular PDFs."""

    if geometria_paginas:
        filas_geometricas = _extraer_programa_analitico_geometrico_pdf(paginas, geometria_paginas)
        if filas_geometricas:
            return filas_geometricas
    return _extraer_programa_analitico_pdf_layout(paginas)


def _reparar_fronteras_programa(filas: list[dict[str, str]]) -> list[dict[str, str]]:
    """Move only source fragments that clearly continue the adjacent visual row."""

    for indice, fila in enumerate(filas[:-1]):
        siguiente = filas[indice + 1]
        continuacion_tema = re.match(r"^([a-záéíóúñ]+)\s+(.+)$", siguiente["tema"])
        if continuacion_tema:
            fila["tema"] = _texto(f"{fila['tema']} {continuacion_tema.group(1)}")
            siguiente["tema"] = continuacion_tema.group(2)

        contenido = fila["contenido"]
        continuacion_contenido = re.match(r"^(.+?[.!?])(?:\s+|$)", siguiente["contenido"])
        if continuacion_contenido and re.search(
            r"\b(?:y|o|de|del|la|el|para|en)\s*$", contenido, re.IGNORECASE
        ):
            texto = continuacion_contenido.group(1)
            fila["contenido"] = _texto(f"{contenido} {texto}")
            siguiente["contenido"] = _texto(siguiente["contenido"][len(texto) :])

    for fila in filas:
        partes = [parte for parte in (fila["tema"], fila["contenido"]) if parte]
        fila["texto"] = f"Semana {fila['semana']} | {' | '.join(partes)}"
    return filas


def _extraer_programa_analitico_pdf_layout(paginas: list[str]) -> list[dict[str, str]]:
    """Rebuild table VI, preserve columns, and discard the evaluation column."""

    lineas: list[tuple[int, str]] = [
        (numero_pagina, _normalizar_linea_pdf(linea, conservar_layout=True))
        for numero_pagina, pagina in enumerate(paginas, start=1)
        for linea in str(pagina or "").splitlines()
    ]
    filas: list[dict[str, str]] = []
    semana_actual = ""
    pagina_actual = ""
    temas_actuales: list[str] = []
    contenidos_actuales: list[str] = []
    fragmentos_sin_marca: list[tuple[str, str]] = []
    dentro_programa = False
    columnas: tuple[int, int | None] | None = None

    def es_encabezado_programa(linea: str) -> bool:
        return all(
            re.search(patron, linea, re.IGNORECASE)
            for patron in (r"\bSemana\b", r"\bTema\b", r"\bContenido\b")
        )

    def inicio_columna(linea: str, patron: str) -> int | None:
        coincidencia = re.search(patron, linea, re.IGNORECASE)
        return coincidencia.start() if coincidencia else None

    def configurar_columnas(indice: int, encabezado: str) -> tuple[int, int | None]:
        inicio_contenido = inicio_columna(encabezado, r"\bContenido\b")
        if inicio_contenido is None:
            return (0, inicio_columna(encabezado, r"\bEvaluaci[oó]n\b"))

        inicio_evaluacion = inicio_columna(encabezado, r"\bEvaluaci[oó]n\b")
        minimo_continuacion = max(28, inicio_contenido - 25)
        candidatos: list[int] = []
        for _, muestra in lineas[indice + 1 :]:
            if es_encabezado_programa(muestra) or re.match(
                r"^\s*(?:VII|VIII|IX)\.\s*", muestra, re.IGNORECASE
            ):
                break
            if not muestra.strip() or _PATRON_SEMANA_PDF.match(muestra):
                continue
            inicio_texto = len(muestra) - len(muestra.lstrip())
            if inicio_texto < minimo_continuacion:
                continue
            if (
                inicio_evaluacion is not None
                and inicio_evaluacion > inicio_contenido
                and inicio_texto >= inicio_evaluacion
            ):
                continue
            candidatos.append(inicio_texto)

        if candidatos:
            inicio_contenido = Counter(candidatos).most_common(1)[0][0]
        return (inicio_contenido, inicio_evaluacion)

    def separar_columnas(linea: str, inicio: int, evaluacion: int | None) -> tuple[str, str]:
        coincidencia = _PATRON_SEMANA_PDF.match(linea)
        inicio_datos = coincidencia.end() if coincidencia else 0
        if evaluacion is not None and evaluacion < inicio:
            tema = linea[inicio_datos:evaluacion]
            contenido = linea[inicio:]
        else:
            tema = linea[inicio_datos:inicio]
            fin_contenido = evaluacion if evaluacion is not None else len(linea)
            contenido = linea[inicio:fin_contenido]
        return _texto(tema), _texto(contenido)

    def agregar_fragmentos(fragmentos: list[tuple[str, str]]) -> None:
        for tema, contenido in fragmentos:
            if tema:
                temas_actuales.append(tema)
            if contenido:
                contenidos_actuales.append(contenido)

    def indice_preludio(fragmentos: list[tuple[str, str]]) -> int:
        for indice in range(len(fragmentos) - 1, -1, -1):
            tema, contenido = fragmentos[indice]
            primer_caracter = tema[:1]
            if tema and primer_caracter.isupper() and (contenido or indice > 0):
                return indice
        return len(fragmentos)

    def preludio_pertenece_a_siguiente_fila(
        fragmentos: list[tuple[str, str]], tema: str, contenido: str
    ) -> bool:
        prelude = _texto(" ".join(contenido for _, contenido in fragmentos))
        if not prelude or not contenido:
            return False
        if contenido[:1].islower():
            return True
        palabras_tema = set(re.findall(r"[a-záéíóúñ]{3,}", tema.casefold()))
        primera_palabra = re.search(r"[a-záéíóúñ]{3,}", contenido.casefold())
        return bool(
            primera_palabra
            and primera_palabra.group(0) in palabras_tema
            and re.search(r"(?:,|\bde|\bdel|\bla|\bel)\s*$", prelude, re.IGNORECASE)
        )

    def cerrar_fila() -> None:
        nonlocal semana_actual, pagina_actual, temas_actuales, contenidos_actuales
        tema = _texto(" ".join(temas_actuales))
        contenido = _texto(" ".join(contenidos_actuales))
        if semana_actual and (tema or contenido):
            partes = [parte for parte in (tema, contenido) if parte]
            filas.append(
                {
                    "semana": semana_actual,
                    "pagina": pagina_actual,
                    "tema": tema,
                    "contenido": contenido,
                    "texto": f"Semana {semana_actual} | {' | '.join(partes)}",
                }
            )
        semana_actual = ""
        pagina_actual = ""
        temas_actuales = []
        contenidos_actuales = []

    for indice, (numero_pagina, linea) in enumerate(lineas):
        if not linea.strip():
            continue
        if re.match(r"^\s*VI\.\s*Programa\s+anal[ií]tico\b", linea, re.IGNORECASE):
            dentro_programa = True
            columnas = None
            fragmentos_sin_marca = []
            continue
        if dentro_programa and re.match(r"^\s*(?:VII|VIII|IX)\.\s*", linea, re.IGNORECASE):
            agregar_fragmentos(fragmentos_sin_marca)
            fragmentos_sin_marca = []
            cerrar_fila()
            return _reparar_fronteras_programa(filas)
        if not dentro_programa:
            continue
        if re.match(r"^\s*Las sesiones de enseñanza\b", linea, re.IGNORECASE):
            agregar_fragmentos(fragmentos_sin_marca)
            fragmentos_sin_marca = []
            cerrar_fila()
            dentro_programa = False
            columnas = None
            continue
        if es_encabezado_programa(linea):
            agregar_fragmentos(fragmentos_sin_marca)
            fragmentos_sin_marca = []
            columnas = configurar_columnas(indice, linea)
            continue
        if columnas is None:
            continue

        tema, contenido = separar_columnas(linea, *columnas)
        if not tema and not contenido:
            continue

        coincidencia = _PATRON_SEMANA_PDF.match(linea)
        if coincidencia:
            preludio: list[tuple[str, str]] = []
            if semana_actual:
                if preludio_pertenece_a_siguiente_fila(fragmentos_sin_marca, tema, contenido):
                    preludio = fragmentos_sin_marca
                else:
                    corte = indice_preludio(fragmentos_sin_marca)
                    agregar_fragmentos(fragmentos_sin_marca[:corte])
                    preludio = fragmentos_sin_marca[corte:]
                cerrar_fila()
            else:
                preludio = fragmentos_sin_marca
            fragmentos_sin_marca = []
            semana_actual = coincidencia.group(1)
            pagina_actual = str(numero_pagina)
            agregar_fragmentos(preludio)
            if tema:
                temas_actuales.append(tema)
            if contenido:
                contenidos_actuales.append(contenido)
            continue

        fragmentos_sin_marca.append((tema, contenido))

    agregar_fragmentos(fragmentos_sin_marca)
    cerrar_fila()
    return _reparar_fronteras_programa(filas)
