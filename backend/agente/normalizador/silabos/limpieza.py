"""Limpieza y extracción estructural de DOCX/PDF curriculares."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

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
from agente.normalizador.silabos import extraccion_curricular as _extraccion_curricular
from agente.normalizador.silabos import extraccion_pdf as _extraccion_pdf
from agente.normalizador.silabos import programa_pdf as _programa_pdf
from agente.normalizador.silabos.analista_llm import analizar_registros_curriculares
from agente.normalizador.silabos.entrada import PATRON_PERIODO, normalizar_periodo
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

_texto_celda_pdf = _programa_pdf._texto_celda_pdf
_extraer_programa_analitico_geometrico_pdf = (
    _programa_pdf._extraer_programa_analitico_geometrico_pdf
)
_extraer_programa_analitico_pdf = _programa_pdf._extraer_programa_analitico_pdf
_reparar_fronteras_programa = _programa_pdf._reparar_fronteras_programa
_extraer_programa_analitico_pdf_layout = _programa_pdf._extraer_programa_analitico_pdf_layout

_PATRON_CODIGO_CURRICULAR = _extraccion_pdf._PATRON_CODIGO_CURRICULAR
_ETIQUETAS_METADATA_PDF = _extraccion_pdf._ETIQUETAS_METADATA_PDF
Document = _extraccion_curricular.Document
_PATRON_REFERENCIA_CURRICULAR = _extraccion_curricular._PATRON_REFERENCIA_CURRICULAR
_SECCIONES_HERRAMIENTAS = _extraccion_curricular._SECCIONES_HERRAMIENTAS
_normalizar_modalidad = _extraccion_curricular._normalizar_modalidad
_texto = _extraccion_curricular._texto
_sin_referencias_curriculares = _extraccion_curricular._sin_referencias_curriculares
_clave = _extraccion_curricular._clave
_hash_id = _extraccion_curricular._hash_id
_ids_curriculares = _extraccion_curricular._ids_curriculares
_hallazgo = _extraccion_curricular._hallazgo
_filas_tabla = _extraccion_curricular._filas_tabla
_es_continuacion_vertical = _extraccion_curricular._es_continuacion_vertical
_codigos = _extraccion_curricular._codigos
_seccion_herramientas = _extraccion_curricular._seccion_herramientas
_herramientas_desde_tabla = _extraccion_curricular._herramientas_desde_tabla
_herramientas_desde_parrafos = _extraccion_curricular._herramientas_desde_parrafos
_deduplicar_evidencias_herramientas = _extraccion_curricular._deduplicar_evidencias_herramientas
_primer_metadata = _extraccion_curricular._primer_metadata
_unir_metadata = _extraccion_curricular._unir_metadata
_nombre_desde_archivo = _extraccion_curricular._nombre_desde_archivo
_ciclo_desde_ruta = _extraccion_curricular._ciclo_desde_ruta


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


_normalizar_linea_pdf = _extraccion_pdf._normalizar_linea_pdf
_normalizar_pdf_para_matching = _extraccion_pdf._normalizar_pdf_para_matching


def _extraer_docx(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
) -> dict[str, object]:
    _extraccion_curricular.Document = Document
    return _extraccion_curricular._extraer_docx(ruta, nombre, carrera, periodo)


def _extraer_pdf(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
) -> dict[str, object]:
    return _extraccion_pdf._extraer_pdf(
        ruta,
        nombre,
        carrera,
        periodo,
        pdf_reader=PdfReader,
        geometria_pdf_pagina=_geometria_pdf_pagina,
    )


_seccion_pdf = _extraccion_pdf._seccion_pdf
_seccion_pdf_raw = _extraccion_pdf._seccion_pdf_raw
_campo_pdf = _extraccion_pdf._campo_pdf
_campo_pdf_metadata = _extraccion_pdf._campo_pdf_metadata
_competencias_pdf = _extraccion_pdf._competencias_pdf
_columna_carrera_pdf = _extraccion_pdf._columna_carrera_pdf
_columna_descripcion_pdf = _extraccion_pdf._columna_descripcion_pdf
_separar_fila_competencia_pdf = _extraccion_pdf._separar_fila_competencia_pdf
_inicia_siguiente_competencia_pdf = _extraccion_pdf._inicia_siguiente_competencia_pdf
_competencias_pdf_lineal = _extraccion_pdf._competencias_pdf_lineal
_logro_general_pdf = _extraccion_pdf._logro_general_pdf
_logros_pdf = _extraccion_pdf._logros_pdf
_punto_v_pdf = _extraccion_pdf._punto_v_pdf
_subseccion_pdf = _extraccion_pdf._subseccion_pdf
_pdf_text_advance = _extraccion_pdf._pdf_text_advance
_geometria_pdf_pagina = _extraccion_pdf._geometria_pdf_pagina
_texto_relevante_pdf = _extraccion_pdf._texto_relevante_pdf
_codigos_curriculares_pdf = _extraccion_pdf._codigos_curriculares_pdf
_evidencias_herramientas_pdf = _extraccion_pdf._evidencias_herramientas_pdf
_ciclo_pdf = _extraccion_pdf._ciclo_pdf


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
