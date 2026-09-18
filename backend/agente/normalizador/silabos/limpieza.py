"""Limpieza y extracción estructural de DOCX/PDF curriculares."""

from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

from docx import Document
from pypdf import PdfReader

from agente.config.settings import ConfiguracionNormalizadorCurricular
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import (
    ArchivoSilabo,
    Hallazgo,
    ProgresoLimpiezaLLM,
    ResultadoLimpiezaSilabos,
    ResultadoValidacionSilabos,
)
from agente.normalizador.silabos import analista_tecnico, salida_catalogos
from agente.normalizador.silabos import programa_pdf as _programa_pdf
from agente.normalizador.silabos.salida_catalogos import ResultadoCatalogosTecnicos

construir_salidas_tecnicas = salida_catalogos.construir_salidas_tecnicas


class _ExtraccionCurricularModule(Protocol):
    Document: Callable[..., object]
    _extraer_docx: Callable[..., dict[str, object]]
    _hallazgo: Callable[..., Hallazgo]


class _ExtraccionPdfModule(Protocol):
    _extraer_pdf: Callable[..., dict[str, object]]
    _geometria_pdf_pagina: Callable[..., object]


def _cargar_modulo(nombre: str) -> object:
    """Load a legacy module only after the selected execution mode is known."""

    return importlib.import_module(nombre)


def _modulo_extraccion_curricular() -> _ExtraccionCurricularModule:
    return cast(
        _ExtraccionCurricularModule,
        _cargar_modulo("agente.normalizador.silabos.extraccion_curricular"),
    )


def _modulo_extraccion_pdf() -> _ExtraccionPdfModule:
    return cast(
        _ExtraccionPdfModule,
        _cargar_modulo("agente.normalizador.silabos.extraccion_pdf"),
    )


def _hallazgo(
    codigo: str,
    severidad: str,
    mensaje: str,
    archivo: str,
    detalle: str | None = None,
) -> Hallazgo:
    return _modulo_extraccion_curricular()._hallazgo(codigo, severidad, mensaje, archivo, detalle)


def _resultado_catalogos_tecnicos_fallback() -> ResultadoCatalogosTecnicos:
    return ResultadoCatalogosTecnicos(
        publicable=False,
        relaciones=0,
        competencias=0,
        pendientes=0,
        outputs=(),
        release_gate={},
    )


_COMPAT_EXPORTS = {
    "_PATRON_REFERENCIA_CURRICULAR": ("extraccion_curricular", "_PATRON_REFERENCIA_CURRICULAR"),
    "_SECCIONES_HERRAMIENTAS": ("extraccion_curricular", "_SECCIONES_HERRAMIENTAS"),
    "_normalizar_modalidad": ("extraccion_curricular", "_normalizar_modalidad"),
    "_texto": ("extraccion_curricular", "_texto"),
    "_sin_referencias_curriculares": ("extraccion_curricular", "_sin_referencias_curriculares"),
    "_clave": ("extraccion_curricular", "_clave"),
    "_hash_id": ("extraccion_curricular", "_hash_id"),
    "_ids_curriculares": ("extraccion_curricular", "_ids_curriculares"),
    "_filas_tabla": ("extraccion_curricular", "_filas_tabla"),
    "_es_continuacion_vertical": ("extraccion_curricular", "_es_continuacion_vertical"),
    "_codigos": ("extraccion_curricular", "_codigos"),
    "_seccion_herramientas": ("extraccion_curricular", "_seccion_herramientas"),
    "_herramientas_desde_tabla": ("extraccion_curricular", "_herramientas_desde_tabla"),
    "_herramientas_desde_parrafos": ("extraccion_curricular", "_herramientas_desde_parrafos"),
    "_deduplicar_evidencias_herramientas": (
        "extraccion_curricular",
        "_deduplicar_evidencias_herramientas",
    ),
    "_primer_metadata": ("extraccion_curricular", "_primer_metadata"),
    "_unir_metadata": ("extraccion_curricular", "_unir_metadata"),
    "_nombre_desde_archivo": ("extraccion_curricular", "_nombre_desde_archivo"),
    "_ciclo_desde_ruta": ("extraccion_curricular", "_ciclo_desde_ruta"),
    "_PATRON_CODIGO_CURRICULAR": ("extraccion_pdf", "_PATRON_CODIGO_CURRICULAR"),
    "_ETIQUETAS_METADATA_PDF": ("extraccion_pdf", "_ETIQUETAS_METADATA_PDF"),
    "_normalizar_linea_pdf": ("extraccion_pdf", "_normalizar_linea_pdf"),
    "_normalizar_pdf_para_matching": ("extraccion_pdf", "_normalizar_pdf_para_matching"),
    "_seccion_pdf": ("extraccion_pdf", "_seccion_pdf"),
    "_seccion_pdf_raw": ("extraccion_pdf", "_seccion_pdf_raw"),
    "_campo_pdf": ("extraccion_pdf", "_campo_pdf"),
    "_campo_pdf_metadata": ("extraccion_pdf", "_campo_pdf_metadata"),
    "_competencias_pdf": ("extraccion_pdf", "_competencias_pdf"),
    "_columna_carrera_pdf": ("extraccion_pdf", "_columna_carrera_pdf"),
    "_columna_descripcion_pdf": ("extraccion_pdf", "_columna_descripcion_pdf"),
    "_separar_fila_competencia_pdf": ("extraccion_pdf", "_separar_fila_competencia_pdf"),
    "_inicia_siguiente_competencia_pdf": ("extraccion_pdf", "_inicia_siguiente_competencia_pdf"),
    "_competencias_pdf_lineal": ("extraccion_pdf", "_competencias_pdf_lineal"),
    "_logro_general_pdf": ("extraccion_pdf", "_logro_general_pdf"),
    "_logros_pdf": ("extraccion_pdf", "_logros_pdf"),
    "_punto_v_pdf": ("extraccion_pdf", "_punto_v_pdf"),
    "_subseccion_pdf": ("extraccion_pdf", "_subseccion_pdf"),
    "_pdf_text_advance": ("extraccion_pdf", "_pdf_text_advance"),
    "_texto_relevante_pdf": ("extraccion_pdf", "_texto_relevante_pdf"),
    "_codigos_curriculares_pdf": ("extraccion_pdf", "_codigos_curriculares_pdf"),
    "_evidencias_herramientas_pdf": ("extraccion_pdf", "_evidencias_herramientas_pdf"),
    "_ciclo_pdf": ("extraccion_pdf", "_ciclo_pdf"),
    "_texto_celda_pdf": ("programa_pdf", "_texto_celda_pdf"),
    "_extraer_programa_analitico_geometrico_pdf": (
        "programa_pdf",
        "_extraer_programa_analitico_geometrico_pdf",
    ),
    "_extraer_programa_analitico_pdf": ("programa_pdf", "_extraer_programa_analitico_pdf"),
    "_reparar_fronteras_programa": ("programa_pdf", "_reparar_fronteras_programa"),
    "_extraer_programa_analitico_pdf_layout": (
        "programa_pdf",
        "_extraer_programa_analitico_pdf_layout",
    ),
}


def _resolver_funcion_compatibilidad(name: str) -> Callable[..., object]:
    module_name, attribute_name = _COMPAT_EXPORTS[name]
    modulo = importlib.import_module(f"agente.normalizador.silabos.{module_name}")
    return cast(Callable[..., object], getattr(modulo, attribute_name))


def _campo_pdf_metadata(*args: object, **kwargs: object) -> str:
    return cast(str, _resolver_funcion_compatibilidad("_campo_pdf_metadata")(*args, **kwargs))


def _competencias_pdf(*args: object, **kwargs: object) -> list[dict[str, str]]:
    return cast(
        list[dict[str, str]],
        _resolver_funcion_compatibilidad("_competencias_pdf")(*args, **kwargs),
    )


def _logros_pdf(*args: object, **kwargs: object) -> list[dict[str, object]]:
    return cast(
        list[dict[str, object]],
        _resolver_funcion_compatibilidad("_logros_pdf")(*args, **kwargs),
    )


def _ids_curriculares(
    carrera: str,
    periodo: str,
    nombre: str,
    codigo_curso: str,
) -> tuple[str, str]:
    return cast(
        tuple[str, str],
        _resolver_funcion_compatibilidad("_ids_curriculares")(
            carrera, periodo, nombre, codigo_curso
        ),
    )


_texto_celda_pdf = _programa_pdf._texto_celda_pdf
_extraer_programa_analitico_geometrico_pdf = (
    _programa_pdf._extraer_programa_analitico_geometrico_pdf
)
_extraer_programa_analitico_pdf = _programa_pdf._extraer_programa_analitico_pdf
_reparar_fronteras_programa = _programa_pdf._reparar_fronteras_programa
_extraer_programa_analitico_pdf_layout = _programa_pdf._extraer_programa_analitico_pdf_layout


_PUBLIC_EXPORTS = (
    "_texto_celda_pdf",
    "_extraer_programa_analitico_geometrico_pdf",
    "_extraer_programa_analitico_pdf",
    "_reparar_fronteras_programa",
    "_extraer_programa_analitico_pdf_layout",
)
__all__ = _PUBLIC_EXPORTS


def _extraer_docx(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
) -> dict[str, object]:
    modulo = _modulo_extraccion_curricular()
    modulo.Document = Document
    return modulo._extraer_docx(ruta, nombre, carrera, periodo)


def _geometria_pdf_pagina(*args: object, **kwargs: object) -> object:
    return _modulo_extraccion_pdf()._geometria_pdf_pagina(*args, **kwargs)


def _extraer_pdf(
    ruta: Path,
    nombre: str,
    carrera: str,
    periodo: str,
) -> dict[str, object]:
    return _modulo_extraccion_pdf()._extraer_pdf(
        ruta,
        nombre,
        carrera,
        periodo,
        pdf_reader=PdfReader,
        geometria_pdf_pagina=_geometria_pdf_pagina,
    )


def limpiar_archivo(
    ruta_entrada: Path,
    directorio_ejecucion: Path,
    validacion: ResultadoValidacionSilabos,
    usar_llm: bool = False,
    al_actualizar_progreso_llm: Callable[[ProgresoLimpiezaLLM], None] | None = None,
    progreso_inicial: ProgresoLimpiezaLLM | None = None,
    id_ejecucion: str = "",
    cancelada: Callable[[], bool] | None = None,
    configuracion_curricular: ConfiguracionNormalizadorCurricular | None = None,
) -> ResultadoLimpiezaSilabos:
    """Materializa una fuente y construye el contrato curricular técnico."""

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
    resultado_catalogo: ResultadoCatalogosTecnicos
    try:
        propuestas_tecnicas: list[dict[str, object]] = []
        auditoria_tecnica: list[dict[str, object]] = []
        propuestas_tecnicas_path = reportes / "propuestas_tecnicas.jsonl"
        analisis_tecnico_path = reportes / "analisis_tecnico.json"
        if not usar_llm:
            analisis_tecnico: dict[str, object] = {
                "estado": "COMPLETADO",
                "modo_analista": "technical",
                "modo_ejecucion": "DETERMINISTICO_SIN_LLM",
                "propuestas_pendientes": 0,
            }
        else:
            assert configuracion_curricular is not None
            try:
                verificar_cancelacion()
                propuestas_tecnicas = analista_tecnico.inferir_competencias_tecnicas(
                    registros,
                    configuracion_curricular,
                    configuracion_curricular.ruta_catalogo_tecnico,
                    auditoria=auditoria_tecnica,
                )
                for advertencia in auditoria_tecnica:
                    hallazgos.append(
                        _hallazgo(
                            str(advertencia.get("codigo") or "SILABO_SIN_PROPUESTA_TECNICA"),
                            "warning",
                            str(
                                advertencia.get("mensaje")
                                or "El sílabo no produjo una propuesta técnica válida."
                            ),
                            validacion.archivo,
                            str(advertencia.get("id_silabo") or ""),
                        )
                    )
                analisis_tecnico = {
                    "estado": (
                        "COMPLETADO_CON_ADVERTENCIAS" if auditoria_tecnica else "COMPLETADO"
                    ),
                    "modo_analista": "technical",
                    "propuestas_pendientes": len(propuestas_tecnicas),
                }
                if auditoria_tecnica:
                    analisis_tecnico["advertencias"] = auditoria_tecnica
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                hallazgos.append(
                    _hallazgo(
                        "ANALISTA_TECNICO_NO_DISPONIBLE",
                        "warning",
                        (
                            "El analista técnico no estuvo disponible; se conserva "
                            "el resultado determinista."
                        ),
                        validacion.archivo,
                        f"{type(exc).__name__}: {str(exc)[:200]}",
                    )
                )
                analisis_tecnico = {
                    "estado": "FALLBACK_DETERMINISTA",
                    "modo_analista": "technical",
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "propuestas_pendientes": 0,
                }

        analista_tecnico.escribir_propuestas_tecnicas(
            propuestas_tecnicas_path,
            propuestas_tecnicas,
        )
        _escribir_json(analisis_tecnico_path, analisis_tecnico)
        resultado_catalogo = construir_salidas_tecnicas(
            registros,
            directorio_ejecucion / "salidas",
            carrera=validacion.carrera,
            periodo_academico=validacion.periodo,
            propuestas_tecnicas=propuestas_tecnicas,
            analisis_tecnico=analisis_tecnico,
        )
        resultado_catalogo = replace(
            resultado_catalogo,
            outputs=tuple(
                resultado_catalogo.outputs
                + (
                    _output(
                        propuestas_tecnicas_path,
                        "propuestas_tecnicas",
                        len(propuestas_tecnicas),
                    ),
                    _output(analisis_tecnico_path, "analisis_tecnico", 1),
                )
            ),
        )
        if usar_llm:
            if analisis_tecnico["estado"] in {
                "COMPLETADO",
                "COMPLETADO_CON_ADVERTENCIAS",
            }:
                mensaje_reporte = (
                    "Reporte técnico disponible con advertencias; requiere revisión HITL."
                    if analisis_tecnico["estado"] == "COMPLETADO_CON_ADVERTENCIAS"
                    else "Reporte técnico disponible."
                )
                publicar_progreso(
                    replace(
                        progreso_extraccion,
                        fase="completado",
                        reporte_final="disponible",
                    ).con_evento(mensaje_reporte)
                )
            else:
                publicar_progreso(
                    replace(
                        progreso_extraccion,
                        fase="error",
                        reporte_final="disponible",
                    ).con_evento(
                        "El análisis técnico no estuvo disponible; continúa la salida determinista."
                    )
                )
    except CancelacionSolicitada:
        analista_tecnico.escribir_propuestas_tecnicas(
            reportes / "propuestas_tecnicas.jsonl",
            (),
        )
        _escribir_json(
            reportes / "analisis_tecnico.json",
            {
                "estado": "CANCELADO",
                "modo_analista": "technical",
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
                ).con_evento("El análisis técnico fue cancelado por el usuario.")
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
                    "No se pudo completar el reporte técnico; se conservan los avances previos."
                )
            )
        hallazgos.append(
            _hallazgo(
                "CATALOGO_TECNICO_NO_DISPONIBLE",
                "error",
                "No se pudo construir el catálogo curricular técnico.",
                validacion.archivo,
                f"{type(exc).__name__}: {str(exc)[:200]}",
            )
        )
        resultado_catalogo = _resultado_catalogos_tecnicos_fallback()

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
