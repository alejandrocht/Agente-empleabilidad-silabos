"""Construcción y validación del contrato CSV curricular.

La fuente curricular se conserva separada de la capa canónica: las
competencias y habilidades fuente permiten auditar exactamente qué declaró el
sílabo, mientras que los catálogos CHH solo contienen conceptos que pudieron
resolverse con evidencia suficiente. Las relaciones fuente y canónicas se
publican en tablas distintas para no convertir una inferencia pendiente en un
nodo curricular inventado.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from agente.normalizador.empleabilidad.catalogo import (
    CatalogoCHH,
    ConceptoCHH,
    clave_concepto,
)
from agente.normalizador.modelos import Hallazgo, ResultadoValidacionSilabos
from agente.normalizador.silabos.analista_llm import (
    DecisionCurricular,
    _clave_herramienta_canonica,
    _coincide_nombre_herramienta_en_texto,
    _herramienta_nueva_evidenciada,
    _nombre_herramienta_canonico,
)

COMPETENCIAS_SCHEMA: tuple[str, ...] = (
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
)
HABILIDADES_SCHEMA: tuple[str, ...] = (
    "id_habilidad",
    "nombre_habilidad",
    "descripcion_breve",
)
HERRAMIENTAS_SCHEMA: tuple[str, ...] = (
    "id_herramienta",
    "nombre_herramienta",
    "descripcion_breve_herramienta",
)
COBERTURA_SCHEMA: tuple[str, ...] = (
    "id_cob_curricular",
    "id_curso",
    "id_silabo",
    "id_competencia",
    "id_habilidad",
    "id_herramienta",
)

ARCHIVOS_SALIDA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("catalogo_competencias.csv", COMPETENCIAS_SCHEMA),
    ("catalogo_habilidades.csv", HABILIDADES_SCHEMA),
    ("catalogo_herramientas.csv", HERRAMIENTAS_SCHEMA),
    ("cobertura_curricular.csv", COBERTURA_SCHEMA),
)

_VERBOS_GENERICOS = {
    "aplicar conceptos",
    "comunicar",
    "integrar",
    "usar herramientas",
}

_PALABRAS_NO_EVIDENCIA = {
    "a", "al", "ante", "bajo", "como", "con", "contra", "cual", "cuales",
    "de", "del", "desde", "donde", "durante", "el", "ella", "ellas", "ellos",
    "en", "entre", "es", "esta", "este", "estos", "la", "las", "lo", "los",
    "mediante", "para", "por", "que", "se", "segun", "sin", "sobre", "su",
    "sus", "un", "una", "unas", "uno", "unos", "y",
    "analiza", "analizar", "aplica", "aplicar", "argumenta", "argumentar",
    "conoce", "conocer", "construye", "construir", "crea", "crear", "describe",
    "describir", "determina", "determinar", "desarrolla", "desarrollar", "diseña",
    "diseñar", "elabora", "elaborar", "evalua", "evaluar", "examina", "examinar",
    "explica", "explicar", "fundamenta", "fundamentar", "genera", "generar",
    "identifica", "identificar", "interpreta", "interpretar", "organiza", "organizar",
    "plantea", "plantear", "propone", "proponer", "reconoce", "reconocer", "realiza",
    "realizar", "selecciona", "seleccionar", "utiliza", "utilizar",
}

TCompetencia = TypeVar("TCompetencia", ConceptoCHH, dict[str, str])


@dataclass(frozen=True, slots=True)
class ResultadoCatalogoCurricular:
    """Resultado del gate de los cuatro CSV curriculares."""

    publicable: bool
    relaciones: int
    competencias: int
    habilidades: int
    herramientas: int
    outputs: tuple[dict[str, object], ...]
    hallazgos: tuple[Hallazgo, ...]
    cuarentena: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class ResolucionConcepto:
    """Resultado auditable de una resolución canónica o textual."""

    concepto: ConceptoCHH | None
    metodo: str
    puntaje: float | None = None
    puntaje_segundo: float | None = None


@dataclass(frozen=True, slots=True)
class HerramientaDetectada:
    """Herramienta encontrada dentro de una sección curricular confiable."""

    concepto: ConceptoCHH
    seccion: str
    texto_evidencia: str
    coincidencia: str


def construir_salidas_curriculares(
    registros: list[dict[str, object]],
    validacion: ResultadoValidacionSilabos,
    directorio_ejecucion: Path,
    catalogo: CatalogoCHH,
    catalogo_carrera: CatalogoCHH | None = None,
    decisiones_llm: dict[str, DecisionCurricular] | None = None,
) -> ResultadoCatalogoCurricular:
    """Normaliza los registros extraídos y escribe las cuatro tablas CSV."""

    salida = directorio_ejecucion / "salidas"
    salida.mkdir(parents=True, exist_ok=True)
    catalogo_curricular = _catalogo_curricular(
        registros,
        catalogo,
        catalogo_carrera,
    )
    decisiones_llm = decisiones_llm or {}
    hallazgos: list[Hallazgo] = []
    cuarentena: list[dict[str, object]] = []
    competencias: dict[str, dict[str, str]] = {}
    competencias_fuente: dict[str, dict[str, object]] = {}
    habilidades: dict[str, dict[str, str]] = {}
    habilidades_fuente: dict[str, dict[str, object]] = {}
    herramientas: dict[str, dict[str, str]] = {}
    herramientas_fuente: dict[str, dict[str, object]] = {}
    relaciones_fuente: set[tuple[str, str, str, str, str]] = set()
    relaciones_canonicas: set[tuple[str, str, str, str, str]] = set()
    carrera_ejecucion = _texto(validacion.carrera).upper()
    periodo_ejecucion = _texto(validacion.periodo)

    for registro in registros:
        datos_objeto = registro.get("datos")
        datos = datos_objeto if isinstance(datos_objeto, dict) else {}
        id_silabo = _texto(registro.get("id_silabo"))
        id_curso = _texto(registro.get("id_curso"))
        archivo = _archivo_origen(registro)
        curso = _texto(datos.get("curso"))
        outcomes = _logros(datos)
        declaraciones = _declaraciones(datos)

        carrera_registro = _texto(registro.get("carrera")).upper()
        periodo_registro = _texto(registro.get("periodo"))
        if (carrera_registro, periodo_registro) != (
            carrera_ejecucion,
            periodo_ejecucion,
        ):
            _error(
                hallazgos,
                cuarentena,
                "REGISTRO_FUERA_DE_CARRERA",
                (
                    "El registro no pertenece a la carrera y periodo declarados "
                    "para esta ejecución."
                ),
                archivo,
                id_silabo,
                (
                    f"registro={carrera_registro}/{periodo_registro}; "
                    f"ejecucion={carrera_ejecucion}/{periodo_ejecucion}"
                ),
            )
            continue

        if not id_silabo or not id_curso:
            _error(
                hallazgos,
                cuarentena,
                "IDENTIDAD_CURRICULAR_INCOMPLETA",
                "El sílabo no tiene id_silabo o id_curso.",
                archivo,
                id_silabo,
            )
            continue

        if not outcomes:
            _error(
                hallazgos,
                cuarentena,
                "CURSO_SIN_LOGRO",
                "El sílabo no contiene un logro utilizable para construir una habilidad.",
                archivo,
                id_silabo,
            )
            continue
        if not declaraciones:
            hallazgos.append(
                Hallazgo(
                    codigo="CURSO_SIN_COMPETENCIA_DECLARADA",
                    severidad="warning",
                    mensaje=(
                        "El sílabo no contiene competencias declaradas; se intentará "
                        "normalizar cada logro usando su evidencia textual."
                    ),
                    hoja=archivo,
                    detalle=id_silabo,
                )
            )

        # La competencia se registra antes de recorrer sus logros. Así una
        # declaración que el sílabo no referenció correctamente no desaparece
        # del catálogo ni se reemplaza por un placeholder.
        competencias_por_declaracion: dict[tuple[str, str], tuple[str, ConceptoCHH]] = {}
        for declaracion in declaraciones:
            resolucion_competencia = _resolver_competencia(catalogo_curricular, declaracion)
            competencia = resolucion_competencia.concepto
            assert competencia is not None
            competencia_fuente = _hash_id(
                "COMP_SRC",
                id_silabo,
                declaracion["codigo"],
                declaracion["nombre"],
            )
            competencias_por_declaracion[
                (declaracion["codigo"], clave_concepto(declaracion["nombre"]))
            ] = (competencia_fuente, competencia)
            competencias_fuente[competencia_fuente] = {
                "id_competencia_fuente": competencia_fuente,
                "id_curso": id_curso,
                "id_silabo": id_silabo,
                "archivo": archivo,
                "codigo_competencia": declaracion["codigo"],
                "nombre_competencia_fuente": declaracion["nombre"],
                "descripcion_fuente": declaracion["descripcion"],
                "id_competencia_canonica": competencia.id,
                "estado_resolucion": "DECLARADA",
                "metodo_resolucion": resolucion_competencia.metodo,
                "puntaje_resolucion": resolucion_competencia.puntaje,
                "puntaje_segundo": resolucion_competencia.puntaje_segundo,
            }
            competencias[competencia.id] = {
                "id_competencia": competencia.id,
                "nombre_competencia": competencia.nombre,
                "descripcion_breve_competencia": competencia.descripcion,
                "tipo_competencia": competencia.tipo,
            }

        hallazgos.extend(
            _hallazgos_consistencia_silabo(
                outcomes,
                declaraciones,
                archivo,
                id_silabo,
            )
        )

        for logro in outcomes:
            descripcion = _texto(logro.get("descripcion"))
            etiqueta = _texto(logro.get("etiqueta"))
            if not descripcion:
                _error(
                    hallazgos,
                    cuarentena,
                    "LOGRO_SIN_HABILIDAD",
                    "El logro específico no tiene descripción observable.",
                    archivo,
                    id_silabo,
                    etiqueta,
                )
                continue

            seleccionadas, codigos_problematicos = _competencias_para_logro(
                logro,
                declaraciones,
                datos,
                descripcion,
                catalogo_curricular,
            )
            if codigos_problematicos:
                declarados_detalle = ", ".join(
                    sorted({item["codigo"] for item in declaraciones})
                ) or "ninguno"
                hallazgos.append(
                    Hallazgo(
                        codigo="LOGRO_CODIGO_INCONSISTENTE",
                        severidad="warning",
                        mensaje=(
                            "El código del logro no coincide de forma unívoca con la "
                            "tabla de competencias; se conserva el logro y se prioriza "
                            "la evidencia textual del sílabo."
                        ),
                        hoja=archivo,
                        detalle=(
                            f"{etiqueta}: códigos problemáticos="
                            f"{', '.join(codigos_problematicos)}; "
                            f"declarados={declarados_detalle}"
                        ),
                    )
                )
            competencias_logro: list[ConceptoCHH] = []
            competencias_fuente_logro: list[str] = []
            for declaracion in seleccionadas:
                resolucion_competencia = _resolver_competencia(catalogo_curricular, declaracion)
                competencia = resolucion_competencia.concepto
                assert competencia is not None
                clave_declaracion = (
                    declaracion["codigo"],
                    clave_concepto(declaracion["nombre"]),
                )
                fuente_resuelta = competencias_por_declaracion.get(clave_declaracion)
                if fuente_resuelta is None:
                    competencia_fuente = _hash_id(
                        "COMP_SRC",
                        id_silabo,
                        declaracion["codigo"],
                        declaracion["nombre"],
                    )
                    competencias_fuente[competencia_fuente] = {
                        "id_competencia_fuente": competencia_fuente,
                        "id_curso": id_curso,
                        "id_silabo": id_silabo,
                        "archivo": archivo,
                        "codigo_competencia": declaracion["codigo"],
                        "nombre_competencia_fuente": declaracion["nombre"],
                        "descripcion_fuente": declaracion["descripcion"],
                        "id_competencia_canonica": competencia.id,
                        "estado_resolucion": "RESUELTA_POR_EVIDENCIA",
                        "metodo_resolucion": _texto(
                            declaracion.get("_metodo_resolucion")
                        ) or resolucion_competencia.metodo,
                        "puntaje_resolucion": declaracion.get("_puntaje_resolucion"),
                        "puntaje_segundo": declaracion.get("_puntaje_segundo"),
                    }
                else:
                    competencia_fuente = fuente_resuelta[0]
                fuente = competencias_fuente[competencia_fuente]
                fuente["metodo_vinculacion_logro"] = _texto(
                    declaracion.get("_metodo_resolucion")
                ) or "CODIGO_DECLARADO"
                fuente["puntaje_vinculacion_logro"] = declaracion.get(
                    "_puntaje_resolucion", 1.0
                )
                fuente["puntaje_segundo_vinculacion"] = declaracion.get(
                    "_puntaje_segundo"
                )
                competencias_fuente_logro.append(competencia_fuente)
                competencias_logro.append(competencia)
                competencias[competencia.id] = {
                    "id_competencia": competencia.id,
                    "nombre_competencia": competencia.nombre,
                    "descripcion_breve_competencia": competencia.descripcion,
                    "tipo_competencia": competencia.tipo,
                }

            # Cada código que el logro trae pero no pudo resolverse se conserva
            # como referencia auditable, aunque además exista una selección
            # textual de una competencia declarada. Nunca se publica como una
            # competencia inventada; solo queda en el reporte y la cobertura
            # fuente para revisión.
            for codigo in codigos_problematicos:
                if codigo == "SIN_CODIGO":
                    continue
                competencia_fuente = _hash_id("COMP_REF", id_silabo, codigo)
                competencias_fuente[competencia_fuente] = {
                    "id_competencia_fuente": competencia_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "archivo": archivo,
                    "codigo_competencia": codigo,
                    "nombre_competencia_fuente": "",
                    "descripcion_fuente": "",
                    "id_competencia_canonica": "",
                    "estado_resolucion": "REFERENCIA_NO_DECLARADA",
                }
                if competencia_fuente not in competencias_fuente_logro:
                    competencias_fuente_logro.append(competencia_fuente)

            id_habilidad_fuente = _hash_id(
                "HAB_SRC",
                id_silabo,
                etiqueta,
                descripcion,
            )
            decision_llm = decisiones_llm.get(id_habilidad_fuente)
            resolucion_habilidad = _resolver_habilidad_canonica(
                catalogo_curricular,
                descripcion,
            )
            habilidad_canonica = resolucion_habilidad.concepto
            competencia_llm: ConceptoCHH | None = None
            if decision_llm is not None:
                competencia_llm = _concepto_decidido(
                    catalogo_curricular,
                    decision_llm.competencia.nombre,
                    decision_llm.competencia.descripcion,
                    decision_llm.competencia.tipo or "dura",
                    "COMP",
                )
                habilidad_canonica = _concepto_decidido(
                    catalogo_curricular,
                    decision_llm.habilidad.nombre,
                    decision_llm.habilidad.descripcion,
                    "habilidad",
                    "HAB",
                )
                competencias_logro_canonicas = [competencia_llm]
            else:
                competencias_logro_canonicas = list(competencias_logro)
            habilidades_fuente[id_habilidad_fuente] = {
                "id_habilidad_fuente": id_habilidad_fuente,
                "id_curso": id_curso,
                "id_silabo": id_silabo,
                "archivo": archivo,
                "etiqueta_logro": etiqueta,
                "descripcion_fuente": descripcion,
                "codigos_competencia": ";".join(_codigos_del_logro(logro)),
                "id_habilidad_canonica": habilidad_canonica.id if habilidad_canonica else "",
                "estado_resolucion": (
                    "LLM_CANONIZADA" if decision_llm is not None
                    else "CANONIZADA" if habilidad_canonica else "REVISAR"
                ),
                "metodo_resolucion": (
                    "LLM_CARRERA" if decision_llm is not None else resolucion_habilidad.metodo
                ),
                "puntaje_resolucion": (
                    decision_llm.confianza if decision_llm is not None
                    else resolucion_habilidad.puntaje
                ),
                "puntaje_segundo": resolucion_habilidad.puntaje_segundo,
                "id_competencia_llm": competencia_llm.id if competencia_llm else "",
            }
            if competencia_llm is not None and not competencias_logro:
                assert decision_llm is not None
                competencia_fuente = _hash_id(
                    "COMP_SRC", id_silabo, "LLM", competencia_llm.nombre
                )
                competencias_fuente[competencia_fuente] = {
                    "id_competencia_fuente": competencia_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "archivo": archivo,
                    "codigo_competencia": "LLM",
                    "nombre_competencia_fuente": competencia_llm.nombre,
                    "descripcion_fuente": decision_llm.competencia.descripcion,
                    "id_competencia_canonica": competencia_llm.id,
                    "estado_resolucion": "LLM_DERIVADA",
                    "metodo_resolucion": "LLM_CARRERA",
                    "puntaje_resolucion": decision_llm.confianza,
                }
                competencias_fuente_logro.append(competencia_fuente)
            if competencia_llm is not None:
                competencias[competencia_llm.id] = {
                    "id_competencia": competencia_llm.id,
                    "nombre_competencia": competencia_llm.nombre,
                    "descripcion_breve_competencia": competencia_llm.descripcion,
                    "tipo_competencia": competencia_llm.tipo,
                }
            if habilidad_canonica is None:
                hallazgos.append(
                    Hallazgo(
                        codigo="HABILIDAD_PENDIENTE_CANONICALIZACION",
                        severidad="warning",
                        mensaje=(
                            "El logro se conserva como habilidad fuente, pero no "
                            "se encontró una habilidad canónica con evidencia suficiente."
                        ),
                        hoja=archivo,
                        detalle=f"{etiqueta}: {descripcion}",
                    )
                )
            else:
                habilidades[habilidad_canonica.id] = {
                    "id_habilidad": habilidad_canonica.id,
                    "nombre_habilidad": habilidad_canonica.nombre,
                    "descripcion_breve": habilidad_canonica.descripcion,
                }

            herramientas_detectadas = _herramientas_explicitas(
                catalogo_curricular,
                _evidencias_herramientas(datos),
            )
            herramientas_nuevas = _herramientas_llm_nuevas(
                decision_llm,
                {**datos, "logro_actual": descripcion},
                herramientas_detectadas,
            )
            herramienta_ids: tuple[str, ...] = tuple(
                deteccion.concepto.id
                for deteccion in herramientas_detectadas
                if decision_llm is None
                or _herramienta_decidida(deteccion.concepto.nombre, decision_llm)
            ) + tuple(herramienta.id for herramienta, _ in herramientas_nuevas)
            for deteccion in herramientas_detectadas:
                if decision_llm is not None and not _herramienta_decidida(
                    deteccion.concepto.nombre, decision_llm
                ):
                    continue
                herramienta = deteccion.concepto
                herramientas[herramienta.id] = {
                    "id_herramienta": herramienta.id,
                    "nombre_herramienta": herramienta.nombre,
                    "descripcion_breve_herramienta": herramienta.descripcion,
                }
                id_herramienta_fuente = _hash_id(
                    "HERR_SRC",
                    id_silabo,
                    etiqueta,
                    herramienta.id,
                    deteccion.seccion,
                    deteccion.texto_evidencia,
                )
                herramientas_fuente[id_herramienta_fuente] = {
                    "id_herramienta_fuente": id_herramienta_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "id_habilidad_fuente": id_habilidad_fuente,
                    "id_herramienta_canonica": herramienta.id,
                    "nombre_herramienta": herramienta.nombre,
                    "seccion_fuente": deteccion.seccion,
                    "texto_evidencia": deteccion.texto_evidencia,
                    "coincidencia": deteccion.coincidencia,
                    "estado_resolucion": "EVIDENCIA_ESTRUCTURADA",
                }
            for herramienta, evidencia in herramientas_nuevas:
                herramientas[herramienta.id] = {
                    "id_herramienta": herramienta.id,
                    "nombre_herramienta": herramienta.nombre,
                    "descripcion_breve_herramienta": herramienta.descripcion,
                }
                id_herramienta_fuente = _hash_id(
                    "HERR_SRC",
                    id_silabo,
                    etiqueta,
                    herramienta.id,
                    evidencia["seccion"],
                    evidencia["texto"],
                )
                herramientas_fuente[id_herramienta_fuente] = {
                    "id_herramienta_fuente": id_herramienta_fuente,
                    "id_curso": id_curso,
                    "id_silabo": id_silabo,
                    "id_habilidad_fuente": id_habilidad_fuente,
                    "id_herramienta_canonica": herramienta.id,
                    "nombre_herramienta": herramienta.nombre,
                    "seccion_fuente": evidencia["seccion"],
                    "texto_evidencia": evidencia["texto"],
                    "coincidencia": herramienta.nombre,
                    "estado_resolucion": "LLM_EVIDENCIA_ESTRUCTURADA",
                }

            for indice_competencia, competencia_fuente in enumerate(competencias_fuente_logro):
                herramientas_fuente_logro = herramienta_ids if indice_competencia == 0 else ()
                for herramienta_id in herramientas_fuente_logro or ("",):
                    relaciones_fuente.add(
                        (
                            id_curso,
                            id_silabo,
                            competencia_fuente,
                            id_habilidad_fuente,
                            herramienta_id,
                        )
                    )

            for competencia in competencias_logro_canonicas:
                for herramienta_id in herramienta_ids or ("",):
                    if habilidad_canonica is not None:
                        relaciones_canonicas.add(
                            (
                                id_curso,
                                id_silabo,
                                competencia.id,
                                habilidad_canonica.id,
                                herramienta_id,
                            )
                        )

            if not competencias_logro:
                _warning(
                    hallazgos,
                    "LOGRO_SIN_COMPETENCIA",
                    (
                        "No se encontró una competencia fuente para el logro; "
                        "se conserva únicamente como evidencia pendiente."
                    ),
                    archivo,
                    id_silabo,
                    etiqueta,
                )
        if not any(
            relacion[0] == id_curso and relacion[1] == id_silabo
            for relacion in relaciones_fuente
        ):
            _error(
                hallazgos,
                cuarentena,
                "CURSO_SIN_COBERTURA",
                "El curso no produjo ninguna relación curricular publicable.",
                archivo,
                id_silabo,
                curso,
            )
    cobertura_canonica = [
        {
            "id_cob_curricular": _hash_id(
                "COB_CUR_CAN",
                id_curso,
                id_silabo,
                id_competencia,
                id_habilidad,
                id_herramienta,
            ),
            "id_curso": id_curso,
            "id_silabo": id_silabo,
            "id_competencia": id_competencia,
            "id_habilidad": id_habilidad,
            "id_herramienta": id_herramienta,
        }
        for id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta in sorted(
            relaciones_canonicas
        )
    ]
    cobertura = cobertura_canonica

    filas_por_archivo: dict[str, list[dict[str, str]]] = {
        "catalogo_competencias.csv": sorted(
            competencias.values(), key=lambda fila: clave_concepto(fila["nombre_competencia"])
        ),
        "catalogo_habilidades.csv": sorted(
            habilidades.values(), key=lambda fila: clave_concepto(fila["nombre_habilidad"])
        ),
        "catalogo_herramientas.csv": sorted(
            herramientas.values(), key=lambda fila: clave_concepto(fila["nombre_herramienta"])
        ),
        "cobertura_curricular.csv": cobertura,
    }
    reportes = salida / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    _escribir_jsonl(reportes / "competencias_fuente.jsonl", competencias_fuente.values())
    _escribir_jsonl(reportes / "habilidades_fuente.jsonl", habilidades_fuente.values())
    _escribir_jsonl(reportes / "herramientas_fuente.jsonl", herramientas_fuente.values())
    _escribir_jsonl(
        reportes / "cobertura_curricular_fuente.jsonl",
        (_fila_cobertura(relacion, "COB_CUR_SRC") for relacion in sorted(relaciones_fuente)),
    )
    _escribir_jsonl(
        reportes / "cobertura_curricular_canonica.jsonl",
        (_fila_cobertura(relacion, "COB_CUR_CAN") for relacion in sorted(relaciones_canonicas)),
    )
    for nombre, columnas in ARCHIVOS_SALIDA:
        ruta = salida / nombre
        _escribir_csv(ruta, columnas, filas_por_archivo[nombre])

    hallazgos_validacion = validar_salidas_curriculares(
        salida,
        registros,
        filas_por_archivo,
        competencias_fuente,
        habilidades_fuente,
        relaciones_canonicas,
    )
    hallazgos.extend(hallazgos_validacion)
    # Los CSV ya escritos siguen siendo evidencia útil incluso cuando el gate
    # los marca como no publicables; declararlos permite inspeccionarlos sin
    # convertirlos en una salida aprobada.
    outputs = [
        _output(salida / nombre, "csv_curricular", len(filas_por_archivo[nombre]))
        for nombre, _ in ARCHIVOS_SALIDA
        if (salida / nombre).is_file()
    ]
    publicable = bool(registros) and not any(
        hallazgo.severidad == "error" for hallazgo in hallazgos
    )
    return ResultadoCatalogoCurricular(
        publicable=publicable,
        relaciones=len(cobertura),
        competencias=len(competencias),
        habilidades=len(habilidades),
        herramientas=len(herramientas),
        outputs=tuple(outputs),
        hallazgos=tuple(hallazgos),
        cuarentena=tuple(cuarentena),
    )


def _catalogo_curricular(
    registros: list[dict[str, object]],
    catalogo_base: CatalogoCHH,
    catalogo_carrera: CatalogoCHH | None,
) -> CatalogoCHH:
    """Construye el alcance de competencias para una ejecución.

    Si existe un catálogo de carrera, ese catálogo es el espacio de búsqueda.
    Si todavía no existe, se crea un perfil provisional con las competencias
    que los propios sílabos declaran. En ambos casos el catálogo global queda
    como vocabulario de resolución exacta, no como generador de competencias
    ajenas al currículo.
    """

    declaraciones_fuente = _declaraciones_de_registros(registros)
    if catalogo_carrera is not None:
        catalogo_por_capas = catalogo_base.con_carrera(
            catalogo_carrera,
            origen="perfil_carrera",
            version="carrera",
        )
        competencias: list[ConceptoCHH] = list(catalogo_carrera.competencias)
        for declaracion in declaraciones_fuente:
            concepto = _concepto_declarado(
                declaracion,
                catalogo_carrera,
                catalogo_base,
            )
            if not any(
                clave_concepto(item.nombre) == clave_concepto(concepto.nombre)
                for item in competencias
            ):
                competencias.append(concepto)
        # La carrera especializa competencias, habilidades y herramientas. El
        # vocabulario general permanece como fallback para no perder conceptos
        # reutilizables mientras el perfil específico aún está incompleto.
        return catalogo_por_capas.con_competencias(
            tuple(competencias),
            origen="perfil_carrera",
            version="carrera",
        )

    competencias = [
        _concepto_declarado(declaracion, None, catalogo_base)
        for declaracion in declaraciones_fuente
    ]
    return catalogo_base.con_competencias(
        tuple(competencias),
        origen="perfil_silabos",
        version="declaraciones",
    )


def _declaraciones_de_registros(
    registros: list[dict[str, object]],
) -> list[dict[str, str]]:
    resultado: list[dict[str, str]] = []
    vistos: set[str] = set()
    for registro in registros:
        datos_objeto = registro.get("datos")
        datos = datos_objeto if isinstance(datos_objeto, dict) else {}
        for declaracion in _declaraciones(datos):
            clave = clave_concepto(declaracion["nombre"])
            if not clave or clave in vistos:
                continue
            vistos.add(clave)
            resultado.append(declaracion)
    return resultado


def _concepto_declarado(
    declaracion: dict[str, str],
    catalogo_carrera: CatalogoCHH | None,
    catalogo_base: CatalogoCHH,
) -> ConceptoCHH:
    nombre = declaracion["nombre"]
    for catalogo in (catalogo_carrera, catalogo_base):
        if catalogo is None:
            continue
        existente = catalogo.obtener("competencia", nombre)
        if existente is not None:
            return existente
    tipo = declaracion.get("tipo") or (
        "blanda" if declaracion.get("codigo", "").startswith("G") else "dura"
    )
    return ConceptoCHH(
        id=_hash_id("COMP", nombre),
        nombre=nombre,
        descripcion=declaracion.get("descripcion", "")
        or f"Capacidad para {nombre.lower()}.",
        tipo=tipo,
    )


def _declaraciones(datos: dict[str, object]) -> list[dict[str, str]]:
    valor = datos.get("competencias_declaradas")
    if not isinstance(valor, list):
        return []
    resultado: list[dict[str, str]] = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        nombre = _texto(item.get("nombre"))
        codigo = _texto(item.get("codigo")).upper()
        # Algunos formatos de tabla repiten literalmente el encabezado
        # ``Nombre`` como si fuera una competencia. No es evidencia curricular
        # y no debe terminar en el catálogo público.
        if nombre and clave_concepto(nombre) != "nombre":
            resultado.append(
                {
                    "codigo": codigo,
                    "nombre": nombre,
                    "descripcion": _texto(item.get("descripcion")),
                }
            )
    return resultado


def _logros(datos: dict[str, object]) -> list[dict[str, object]]:
    valor = datos.get("logros_especificos")
    if isinstance(valor, list):
        return [item for item in valor if isinstance(item, dict)]
    return []


def _hallazgos_consistencia_silabo(
    outcomes: list[dict[str, object]],
    declaraciones: list[dict[str, str]],
    archivo: str,
    id_silabo: str,
) -> list[Hallazgo]:
    """Valida el mapa Lx→G/Ex sin convertir una inconsistencia en pérdida de evidencia."""

    hallazgos: list[Hallazgo] = []
    por_codigo: dict[str, list[dict[str, str]]] = {}
    for declaracion in declaraciones:
        por_codigo.setdefault(declaracion["codigo"], []).append(declaracion)

    duplicados = sorted(
        codigo
        for codigo, items in por_codigo.items()
        if codigo and len({clave_concepto(item["nombre"]) for item in items}) > 1
    )
    if duplicados:
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_CODIGO_DUPLICADO",
                severidad="warning",
                mensaje=(
                    "El sílabo asigna un mismo código a más de una competencia; "
                    "la selección se resolverá por el texto del logro."
                ),
                hoja=archivo,
                detalle=f"códigos={', '.join(duplicados)}; id_silabo={id_silabo}",
            )
        )

    etiquetas = [
        _texto(logro.get("etiqueta")).upper()
        for logro in outcomes
        if _texto(logro.get("etiqueta"))
    ]
    etiquetas_duplicadas = sorted(
        etiqueta for etiqueta in set(etiquetas) if etiquetas.count(etiqueta) > 1
    )
    if etiquetas_duplicadas:
        hallazgos.append(
            Hallazgo(
                codigo="LOGRO_ETIQUETA_DUPLICADA",
                severidad="warning",
                mensaje=(
                    "El sílabo repite una etiqueta de logro; se conservarán las "
                    "descripciones como evidencias independientes."
                ),
                hoja=archivo,
                detalle=(
                    f"etiquetas={', '.join(etiquetas_duplicadas)}; "
                    f"id_silabo={id_silabo}"
                ),
            )
        )

    usados = {
        codigo
        for logro in outcomes
        for codigo in _codigos_del_logro(logro)
    }
    declarados = {item["codigo"] for item in declaraciones if item["codigo"]}
    no_declarados = sorted(usados - declarados)
    if no_declarados:
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_REFERENCIADA_NO_DECLARADA",
                severidad="warning",
                mensaje=(
                    "Un logro referencia códigos que no aparecen en la tabla de "
                    "competencias del mismo sílabo; se conservará su evidencia."
                ),
                hoja=archivo,
                detalle=(
                    f"códigos={', '.join(no_declarados)}; "
                    f"id_silabo={id_silabo}"
                ),
            )
        )
    no_usados = sorted(declarados - usados)
    if no_usados:
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_DECLARADA_SIN_LOGRO",
                severidad="warning",
                mensaje=(
                    "El sílabo declara competencias que no aparecen referenciadas "
                    "por ningún logro específico."
                ),
                hoja=archivo,
                detalle=f"códigos={', '.join(no_usados)}; id_silabo={id_silabo}",
            )
        )
    return hallazgos


def _competencias_para_logro(
    logro: dict[str, object],
    declaraciones: list[dict[str, str]],
    datos: dict[str, object],
    descripcion: str,
    catalogo: CatalogoCHH,
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    codigos = set(_codigos_del_logro(logro))

    por_codigo: dict[str, list[dict[str, str]]] = {}
    for declaracion in declaraciones:
        por_codigo.setdefault(declaracion["codigo"], []).append(declaracion)

    vinculadas: list[dict[str, str]] = []
    codigos_problematicos: set[str] = set()
    if not codigos:
        codigos_problematicos.add("SIN_CODIGO")
    for codigo in sorted(codigos):
        candidatas = por_codigo.get(codigo, [])
        if len(candidatas) == 1:
            vinculadas.append(candidatas[0])
        else:
            # Un código ausente o repetido no puede anular lo que el logro dice.
            codigos_problematicos.add(codigo)

    if not codigos_problematicos and vinculadas:
        return _deduplicar_declaraciones(vinculadas), ()

    # Cuando el código está ausente, repetido o no aparece en la tabla, primero
    # se intenta relacionar el logro con las competencias que el propio sílabo
    # declaró. Así una coincidencia del catálogo no puede reemplazar la fuente.
    textuales_declaradas = _competencias_declaradas_por_texto(
        declaraciones,
        datos,
        descripcion,
    )
    seleccionadas = _deduplicar_declaraciones(vinculadas + textuales_declaradas)
    if seleccionadas:
        return seleccionadas, tuple(sorted(codigos_problematicos))

    if len(declaraciones) == 1 and codigos_problematicos <= {"SIN_CODIGO"}:
        return declaraciones, tuple(sorted(codigos_problematicos))

    # Si el sílabo sí declara competencias, no se permite que el catálogo
    # reemplace esa fuente. El catálogo solo puede ayudar a sílabos que no
    # traen tabla de competencias.
    if not declaraciones:
        textuales_catalogo = _competencias_por_texto(catalogo, datos, descripcion)
        if textuales_catalogo:
            return textuales_catalogo, tuple(sorted(codigos_problematicos))

    # La referencia se conserva en el reporte de fuente, no como una
    # competencia inventada dentro del catálogo canónico.
    return [], tuple(sorted(codigos_problematicos))


def _codigos_del_logro(logro: dict[str, object]) -> tuple[str, ...]:
    valor = logro.get("codigos_competencia")
    if not isinstance(valor, list):
        return ()
    return tuple(
        dict.fromkeys(
            _texto(codigo).upper()
            for codigo in valor
            if _texto(codigo)
        )
    )


def _competencias_por_texto(
    catalogo: CatalogoCHH,
    datos: dict[str, object],
    descripcion: str,
) -> list[dict[str, str]]:
    """Encuentra una competencia canónica usando primero la evidencia curricular."""

    evidencia_logro = _tokens_evidencia(descripcion)
    contexto = _contexto_curricular(datos, descripcion)
    evidencia_contexto = _tokens_evidencia(contexto)
    puntuadas: list[tuple[int, ConceptoCHH]] = []
    for candidato in catalogo.competencias:
        tokens_nombre = _tokens_evidencia(candidato.nombre)
        tokens_descripcion = _tokens_evidencia(candidato.descripcion)
        coincidencias_directas = _coincidencias(evidencia_logro, tokens_nombre)
        coincidencias_descripcion = _coincidencias(evidencia_logro, tokens_descripcion)
        if not coincidencias_directas and not coincidencias_descripcion:
            continue
        puntaje = (
            8 * len(coincidencias_directas)
            + 2 * len(coincidencias_descripcion)
            + 3 * len(_coincidencias(evidencia_contexto, tokens_nombre))
            + len(_coincidencias(evidencia_contexto, tokens_descripcion))
        )
        nombre_clave = clave_concepto(candidato.nombre)
        if nombre_clave and nombre_clave in clave_concepto(contexto):
            puntaje += 20
        if puntaje:
            puntuadas.append((puntaje, candidato))

    seleccion = _seleccionar_competencia_por_puntaje(
        puntuadas,
        lambda candidato: candidato.nombre,
    )
    if seleccion is None:
        return []
    mejor_puntaje, segundo_puntaje, mejor = seleccion
    declaracion = _declaracion_desde_catalogo(mejor)
    declaracion["_metodo_resolucion"] = "COINCIDENCIA_TEXTUAL_CATALOGO"
    declaracion["_puntaje_resolucion"] = str(mejor_puntaje)
    declaracion["_puntaje_segundo"] = str(segundo_puntaje) if segundo_puntaje else ""
    return [declaracion]


def _competencias_declaradas_por_texto(
    declaraciones: list[dict[str, str]],
    datos: dict[str, object],
    descripcion: str,
) -> list[dict[str, str]]:
    evidencia_logro = _tokens_evidencia(descripcion)
    evidencia_contexto = _tokens_evidencia(_contexto_curricular(datos, descripcion))
    puntuadas: list[tuple[int, dict[str, str]]] = []
    for declaracion in declaraciones:
        tokens_nombre = _tokens_evidencia(declaracion["nombre"])
        tokens_descripcion = _tokens_evidencia(declaracion["descripcion"])
        coincidencias_directas = _coincidencias(evidencia_logro, tokens_nombre)
        coincidencias_descripcion = _coincidencias(evidencia_logro, tokens_descripcion)
        if not coincidencias_directas and not coincidencias_descripcion:
            continue
        puntaje = (
            8 * len(coincidencias_directas)
            + 2 * len(coincidencias_descripcion)
            + 3 * len(_coincidencias(evidencia_contexto, tokens_nombre))
            + len(_coincidencias(evidencia_contexto, tokens_descripcion))
        )
        if puntaje:
            puntuadas.append((puntaje, declaracion))
    seleccion = _seleccionar_competencia_por_puntaje(
        puntuadas,
        lambda candidata: candidata["nombre"],
    )
    if seleccion is None:
        return []
    mejor_puntaje, segundo_puntaje, mejor = seleccion
    resultado = dict(mejor)
    resultado["_metodo_resolucion"] = "COINCIDENCIA_TEXTUAL_DECLARADA"
    resultado["_puntaje_resolucion"] = str(mejor_puntaje)
    resultado["_puntaje_segundo"] = str(segundo_puntaje) if segundo_puntaje else ""
    return [resultado]


def _seleccionar_competencia_por_puntaje(
    puntuadas: list[tuple[int, TCompetencia]],
    nombre: Callable[[TCompetencia], str],
) -> tuple[int, int, TCompetencia] | None:
    """Acepta el fallback textual solo con evidencia y separación suficientes."""

    if not puntuadas:
        return None
    puntuadas.sort(
        key=lambda par: (
            -par[0],
            clave_concepto(nombre(par[1])),
        )
    )
    mejor_puntaje, mejor = puntuadas[0]
    segundo_puntaje = puntuadas[1][0] if len(puntuadas) > 1 else 0
    # El fallback no puede elegir una competencia por una palabra genérica ni
    # resolver empates: para esos casos la evidencia queda en revisión.
    if mejor_puntaje < 8 or (
        len(puntuadas) > 1 and mejor_puntaje - segundo_puntaje < 3
    ):
        return None
    return mejor_puntaje, segundo_puntaje, mejor


def _contexto_curricular(datos: dict[str, object], descripcion: str) -> str:
    partes = [
        descripcion,
        _texto(datos.get("curso")),
        _texto(datos.get("sumilla")),
        _texto(datos.get("logro_general")),
        _texto(datos.get("texto_relevante")),
    ]
    programa = datos.get("programa_analitico")
    if isinstance(programa, list):
        partes.extend(_texto(item) for item in programa)
    return " ".join(parte for parte in partes if parte)


def _tokens_evidencia(texto: str) -> set[str]:
    tokens = {
        token
        for token in clave_concepto(texto).split()
        if len(token) >= 4 and token not in _PALABRAS_NO_EVIDENCIA
    }
    return tokens | {token[:6] for token in tokens if len(token) >= 6}


def _coincidencias(origen: set[str], destino: set[str]) -> set[str]:
    return {token for token in origen if token in destino}


def _declaracion_desde_catalogo(candidato: ConceptoCHH) -> dict[str, str]:
    return {
        "codigo": "",
        "nombre": candidato.nombre,
        "descripcion": candidato.descripcion,
        "tipo": candidato.tipo,
    }


def _deduplicar_declaraciones(
    declaraciones: list[dict[str, str]],
) -> list[dict[str, str]]:
    resultado: list[dict[str, str]] = []
    vistos: set[str] = set()
    for declaracion in declaraciones:
        clave = clave_concepto(declaracion["nombre"])
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        resultado.append(declaracion)
    return resultado


def _resolver_competencia(
    catalogo: CatalogoCHH,
    declaracion: dict[str, str],
) -> ResolucionConcepto:
    nombre = declaracion["nombre"]
    existente = catalogo.obtener("competencia", nombre)
    tipo = declaracion.get("tipo") or (
        "blanda" if declaracion.get("codigo", "").startswith("G") else "dura"
    )
    descripcion = declaracion["descripcion"] or f"Capacidad para {nombre.lower()}."
    if existente is not None:
        # El nombre/descrición declarados por el sílabo prevalecen sobre la
        # descripción del catálogo compartido.
        return ResolucionConcepto(
            ConceptoCHH(existente.id, nombre, descripcion, tipo or existente.tipo),
            "NOMBRE_EXACTO",
            1.0,
        )
    return ResolucionConcepto(
        ConceptoCHH(
            id=_hash_id("COMP", nombre),
            nombre=nombre,
            descripcion=descripcion,
            tipo=tipo,
        ),
        "DECLARACION_SILABO",
        1.0,
    )


def _resolver_habilidad_canonica(
    catalogo: CatalogoCHH,
    descripcion: str,
) -> ResolucionConcepto:
    """Resuelve habilidades por nombre o descripción, con umbral y margen."""

    nombre_fuente = _nombre_habilidad(descripcion)
    exacto = catalogo.obtener("habilidad", nombre_fuente)
    if exacto is not None:
        return ResolucionConcepto(exacto, "NOMBRE_EXACTO", 1.0)

    evidencia = _tokens_evidencia(descripcion)
    candidatos: list[tuple[float, str, ConceptoCHH]] = []
    for candidato in catalogo.habilidades:
        tokens_nombre = _tokens_evidencia(candidato.nombre)
        tokens_descripcion = _tokens_evidencia(candidato.descripcion)
        if len(tokens_nombre | tokens_descripcion) < 2:
            continue
        cobertura_nombre = (
            len(evidencia & tokens_nombre) / len(tokens_nombre)
            if tokens_nombre
            else 0.0
        )
        cobertura_descripcion = (
            len(evidencia & tokens_descripcion) / len(tokens_descripcion)
            if tokens_descripcion
            else 0.0
        )
        cobertura = max(cobertura_nombre, cobertura_descripcion)
        if cobertura < 0.75:
            continue
        frase = clave_concepto(candidato.nombre) in clave_concepto(descripcion)
        score = cobertura + (0.35 if frase else 0.0)
        metodo = (
            "COINCIDENCIA_NOMBRE"
            if cobertura_nombre >= cobertura_descripcion
            else "COINCIDENCIA_DESCRIPCION"
        )
        candidatos.append((score, metodo, candidato))

    candidatos.sort(key=lambda item: (-item[0], clave_concepto(item[2].nombre)))
    if not candidatos:
        return ResolucionConcepto(None, "SIN_CANDIDATA")
    mejor_score, metodo, mejor = candidatos[0]
    segundo_score = candidatos[1][0] if len(candidatos) > 1 else 0.0
    if mejor_score < 0.85 or (
        len(candidatos) > 1 and mejor_score - segundo_score < 0.15
    ):
        return ResolucionConcepto(
            None,
            "AMBIGUA_O_INSUFICIENTE",
            round(mejor_score, 3),
            round(segundo_score, 3) if segundo_score else None,
        )
    return ResolucionConcepto(
        mejor,
        metodo,
        round(mejor_score, 3),
        round(segundo_score, 3) if segundo_score else None,
    )


def _herramientas_explicitas(
    catalogo: CatalogoCHH,
    evidencias: tuple[dict[str, str], ...],
) -> tuple[HerramientaDetectada, ...]:
    """Busca herramientas únicamente en secciones estructuradas confiables."""

    encontrados: list[HerramientaDetectada] = []
    vistos: set[str] = set()
    herramientas_ordenadas = sorted(
        catalogo.herramientas,
        key=lambda item: len(item.nombre),
        reverse=True,
    )
    for herramienta in herramientas_ordenadas:
        nombre = herramienta.nombre.strip().lower()
        if len(nombre) < 2:
            continue
        variantes = {nombre}
        if nombre.startswith("microsoft "):
            producto = nombre.removeprefix("microsoft ")
            variantes.update({"ms " + producto, producto})
        for evidencia in evidencias:
            texto = evidencia["texto"]
            texto_normalizado = texto.lower()
            coincidencia = next(
                (
                    variante
                    for variante in variantes
                    if re.search(
                        rf"(?<![a-z0-9]){re.escape(variante)}(?![a-z0-9])",
                        texto_normalizado,
                    )
                ),
                None,
            )
            if coincidencia is None:
                continue
            clave = "|".join(
                (herramienta.id, evidencia["seccion"], texto, coincidencia)
            )
            if clave not in vistos:
                vistos.add(clave)
                encontrados.append(
                    HerramientaDetectada(
                        herramienta,
                        evidencia["seccion"],
                        texto,
                        coincidencia,
                    )
                )
    return tuple(encontrados)


def _evidencias_herramientas(datos: dict[str, object]) -> tuple[dict[str, str], ...]:
    valor = datos.get("herramientas_evidencia")
    if not isinstance(valor, list):
        return ()
    evidencias: list[dict[str, str]] = []
    for item in valor:
        if not isinstance(item, dict):
            continue
        seccion = _texto(item.get("seccion"))
        texto = _texto(item.get("texto"))
        if seccion and texto:
            evidencias.append({"seccion": seccion, "texto": texto})
    return tuple(evidencias)


def _evidencias_herramientas_candidatas(
    datos: dict[str, object],
) -> tuple[dict[str, str], ...]:
    """Añade el logro actual como evidencia auditable sin alterar el contrato CSV."""

    evidencias = list(_evidencias_herramientas(datos))
    logro_actual = _texto(datos.get("logro_actual"))
    if logro_actual:
        evidencias.append({"seccion": "Logro de aprendizaje", "texto": logro_actual})
    return tuple(evidencias)


def _nombre_habilidad(descripcion: str) -> str:
    texto = re.sub(r"^L\d+\s*[-:.)]?\s*", "", descripcion.strip(), flags=re.IGNORECASE)
    texto = texto.rstrip(" .;:")
    return texto[:1].upper() + texto[1:] if texto else ""


def _archivo_origen(registro: dict[str, object]) -> str:
    origen = registro.get("origen")
    return _texto(origen.get("archivo")) if isinstance(origen, dict) else ""


def _concepto_decidido(
    catalogo: CatalogoCHH,
    nombre: str,
    descripcion: str,
    tipo: str,
    prefijo: str,
) -> ConceptoCHH:
    """Resuelve una propuesta LLM sin permitir que el modelo fabrique IDs."""

    existente = catalogo.obtener(
        "competencia" if prefijo == "COMP" else "habilidad",
        nombre,
    )
    if existente is not None:
        return existente
    return ConceptoCHH(
        id=_hash_id(prefijo, nombre),
        nombre=_texto(nombre),
        descripcion=_texto(descripcion) or f"Capacidad curricular para {_texto(nombre).lower()}.",
        tipo=_tipo_competencia(tipo) if prefijo == "COMP" else tipo,
    )


def _tipo_competencia(tipo: str) -> str:
    """Reduce etiquetas LLM a los dos valores permitidos por el contrato CSV."""

    clave = clave_concepto(tipo)
    if "blanda" in clave or "soft" in clave:
        return "blanda"
    return "dura"


def _herramienta_decidida(nombre: str, decision: DecisionCurricular) -> bool:
    """Limita las herramientas publicadas a las detectadas por Python."""

    clave = _clave_herramienta_canonica(nombre)
    return any(
        _clave_herramienta_canonica(item.nombre) == clave
        for item in decision.herramientas
    )


def _herramientas_llm_nuevas(
    decision: DecisionCurricular | None,
    datos: dict[str, object],
    detectadas: tuple[HerramientaDetectada, ...],
) -> tuple[tuple[ConceptoCHH, dict[str, str]], ...]:
    """Crea herramientas nuevas solo cuando el sílabo las respalda literalmente."""

    if decision is None:
        return ()
    existentes = {
        _clave_herramienta_canonica(item.concepto.nombre) for item in detectadas
    }
    resultado: list[tuple[ConceptoCHH, dict[str, str]]] = []
    evidencias = _evidencias_herramientas_candidatas(datos)
    for propuesta in decision.herramientas:
        nombre_canonico = _nombre_herramienta_canonico(propuesta.nombre)
        clave_canonica = _clave_herramienta_canonica(nombre_canonico)
        if clave_canonica in existentes:
            continue
        caso: dict[str, object] = {"evidencia_herramientas_candidata": list(evidencias)}
        if not _herramienta_nueva_evidenciada(nombre_canonico, propuesta.evidencia, caso):
            continue
        evidencia = next(
            (
                item
                for item in evidencias
                if _coincide_nombre_herramienta_en_texto(
                    nombre_canonico, item["texto"]
                )
            ),
            None,
        )
        if evidencia is None:
            continue
        concepto = ConceptoCHH(
            id=_hash_id("HERR", nombre_canonico),
            nombre=nombre_canonico,
            descripcion=_texto(propuesta.evidencia)
            or f"Herramienta curricular: {nombre_canonico}.",
            tipo="herramienta",
        )
        resultado.append((concepto, evidencia))
        existentes.add(clave_canonica)
    return tuple(resultado)


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _hash_id(prefijo: str, *partes: str) -> str:
    payload = "|".join(clave_concepto(parte) for parte in partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _error(
    hallazgos: list[Hallazgo],
    cuarentena: list[dict[str, object]],
    codigo: str,
    mensaje: str,
    archivo: str,
    id_silabo: str,
    detalle: str = "",
) -> None:
    hallazgos.append(
        Hallazgo(
            codigo=codigo,
            severidad="error",
            mensaje=mensaje,
            hoja=archivo or None,
            detalle=detalle or id_silabo,
        )
    )
    cuarentena.append(
        {
            "id_silabo": id_silabo,
            "archivo": archivo,
            "codigo": codigo,
            "mensaje": mensaje,
            "detalle": detalle,
        }
    )


def _warning(
    hallazgos: list[Hallazgo],
    codigo: str,
    mensaje: str,
    archivo: str,
    id_silabo: str,
    detalle: str = "",
) -> None:
    hallazgos.append(
        Hallazgo(
            codigo=codigo,
            severidad="warning",
            mensaje=mensaje,
            hoja=archivo or None,
            detalle=detalle or id_silabo,
        )
    )


def _fila_cobertura(
    relacion: tuple[str, str, str, str, str],
    prefijo: str,
) -> dict[str, str]:
    id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta = relacion
    return {
        "id_cob_curricular": _hash_id(
            prefijo,
            id_curso,
            id_silabo,
            id_competencia,
            id_habilidad,
            id_herramienta,
        ),
        "id_curso": id_curso,
        "id_silabo": id_silabo,
        "id_competencia": id_competencia,
        "id_habilidad": id_habilidad,
        "id_herramienta": id_herramienta,
    }


def _escribir_jsonl(ruta: Path, filas: Iterable[object]) -> None:
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")))
            archivo.write("\n")


def validar_salidas_curriculares(
    salida: Path,
    registros: list[dict[str, object]],
    filas_por_archivo: dict[str, list[dict[str, str]]],
    competencias_fuente: dict[str, dict[str, object]],
    habilidades_fuente: dict[str, dict[str, object]],
    relaciones_canonicas: set[tuple[str, str, str, str, str]],
) -> tuple[Hallazgo, ...]:
    """Actúa como juez determinista antes de publicar los cuatro CSV."""

    hallazgos: list[Hallazgo] = []
    esquemas = {
        "catalogo_competencias.csv": COMPETENCIAS_SCHEMA,
        "catalogo_habilidades.csv": HABILIDADES_SCHEMA,
        "catalogo_herramientas.csv": HERRAMIENTAS_SCHEMA,
        "cobertura_curricular.csv": COBERTURA_SCHEMA,
    }
    filas_leidas: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in esquemas.items():
        ruta = salida / nombre
        if not ruta.is_file():
            hallazgos.append(
                Hallazgo(
                    codigo="CSV_SALIDA_AUSENTE",
                    severidad="error",
                    mensaje="Falta un CSV curricular requerido.",
                    hoja=nombre,
                )
            )
            continue
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            encabezado = tuple(lector.fieldnames or ())
            if encabezado != columnas:
                hallazgos.append(
                    Hallazgo(
                        codigo="CSV_ESQUEMA_INVALIDO",
                        severidad="error",
                        mensaje="El CSV no conserva exactamente el esquema del catálogo.",
                        hoja=nombre,
                        detalle=f"esperado={columnas}; recibido={encabezado}",
                    )
                )
            filas_leidas[nombre] = list(lector)

    competencias_csv = filas_leidas.get("catalogo_competencias.csv", [])
    habilidades_csv = filas_leidas.get("catalogo_habilidades.csv", [])
    herramientas_csv = filas_leidas.get("catalogo_herramientas.csv", [])
    cobertura_csv = filas_leidas.get("cobertura_curricular.csv", [])
    ids_competencias = _ids_unicos(
        competencias_csv,
        "id_competencia",
        "COMPETENCIA_ID_DUPLICADO",
        hallazgos,
    )
    ids_habilidades = _ids_unicos(
        habilidades_csv,
        "id_habilidad",
        "HABILIDAD_ID_DUPLICADO",
        hallazgos,
    )
    ids_herramientas = _ids_unicos(
        herramientas_csv,
        "id_herramienta",
        "HERRAMIENTA_ID_DUPLICADO",
        hallazgos,
    )
    _ids_unicos(
        cobertura_csv,
        "id_cob_curricular",
        "COBERTURA_ID_DUPLICADO",
        hallazgos,
    )

    for fila in competencias_csv:
        nombre = _texto(fila.get("nombre_competencia"))
        if nombre.lower().startswith("competencia referenciada por el sílabo"):
            hallazgos.append(
                Hallazgo(
                    codigo="COMPETENCIA_PLACEHOLDER_PUBLICADA",
                    severidad="error",
                    mensaje="El catálogo no puede publicar competencias placeholder.",
                    hoja="catalogo_competencias.csv",
                    detalle=nombre,
                )
            )

    ids_habilidad_fuente = set(habilidades_fuente)
    for fila in cobertura_csv:
        for columna in ("id_curso", "id_silabo"):
            if not _texto(fila.get(columna)):
                hallazgos.append(
                    Hallazgo(
                        codigo="COBERTURA_IDENTIDAD_AUSENTE",
                        severidad="error",
                        mensaje="La cobertura debe conservar el curso y sílabo de origen.",
                        hoja="cobertura_curricular.csv",
                        campo=columna,
                    )
                )
        competencia_id = _texto(fila.get("id_competencia"))
        habilidad_id = _texto(fila.get("id_habilidad"))
        herramienta_id = _texto(fila.get("id_herramienta"))
        if competencia_id not in ids_competencias:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_COMPETENCIA_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a una competencia que no existe en el CSV.",
                    hoja="cobertura_curricular.csv",
                    detalle=competencia_id,
                )
            )
        if habilidad_id not in ids_habilidades:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_HABILIDAD_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a una habilidad que no existe en el CSV.",
                    hoja="cobertura_curricular.csv",
                    detalle=habilidad_id,
                )
            )
        if herramienta_id and herramienta_id not in ids_herramientas:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_HERRAMIENTA_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a una herramienta que no existe en el CSV.",
                    hoja="cobertura_curricular.csv",
                    detalle=herramienta_id,
                )
            )

    ids_cobertura_canonica = {
        (id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta)
        for id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta
        in relaciones_canonicas
    }
    csv_cobertura = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_habilidad")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in cobertura_csv
    }
    if not csv_cobertura.issubset(ids_cobertura_canonica):
        hallazgos.append(
            Hallazgo(
                codigo="COBERTURA_NO_CANONICA",
                severidad="error",
                mensaje="La cobertura CSV contiene relaciones que no pasaron el flujo canónico.",
                hoja="cobertura_curricular.csv",
            )
        )

    declaraciones = _declaraciones_de_registros(registros)
    nombres_declarados = {
        clave_concepto(declaracion["nombre"]) for declaracion in declaraciones
    }
    nombres_publicados = {
        clave_concepto(fila.get("nombre_competencia", "")) for fila in competencias_csv
    }
    if not nombres_declarados.issubset(nombres_publicados):
        faltantes = sorted(nombres_declarados - nombres_publicados)
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_FUENTE_PERDIDA",
                severidad="error",
                mensaje="Una competencia declarada por el sílabo no llegó al catálogo.",
                hoja="catalogo_competencias.csv",
                detalle="; ".join(faltantes),
            )
        )

    if (
        not (salida / "reportes" / "competencias_fuente.jsonl").is_file()
        or (not competencias_fuente and declaraciones)
    ):
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_FUENTE_NO_AUDITADA",
                severidad="error",
                mensaje="No se generó el reporte de competencias fuente.",
                hoja="reportes/competencias_fuente.jsonl",
            )
        )
    if (
        not (salida / "reportes" / "habilidades_fuente.jsonl").is_file()
        or (
            not ids_habilidad_fuente
            and any(_logros(datos) for datos in _datos_registros(registros))
        )
    ):
        hallazgos.append(
            Hallazgo(
                codigo="HABILIDAD_FUENTE_NO_AUDITADA",
                severidad="error",
                mensaje="No se generó el reporte de habilidades fuente.",
                hoja="reportes/habilidades_fuente.jsonl",
            )
        )
    return tuple(hallazgos)


def _ids_unicos(
    filas: list[dict[str, str]],
    columna: str,
    codigo: str,
    hallazgos: list[Hallazgo],
) -> set[str]:
    ids: set[str] = set()
    for fila in filas:
        identificador = _texto(fila.get(columna))
        if not identificador:
            hallazgos.append(
                Hallazgo(
                    codigo="CSV_ID_AUSENTE",
                    severidad="error",
                    mensaje="Una fila de catálogo no tiene identificador.",
                    campo=columna,
                )
            )
        elif identificador in ids:
            hallazgos.append(
                Hallazgo(
                    codigo=codigo,
                    severidad="error",
                    mensaje="Un identificador aparece más de una vez en el CSV.",
                    campo=columna,
                    detalle=identificador,
                )
            )
        ids.add(identificador)
    return ids


def _datos_registros(registros: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        datos
        for registro in registros
        if isinstance((datos := registro.get("datos")), dict)
    ]


def _escribir_csv(ruta: Path, columnas: tuple[str, ...], filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="raise")
        escritor.writeheader()
        escritor.writerows(
            {columna: fila.get(columna, "") for columna in columnas} for fila in filas
        )


def _output(ruta: Path, tipo: str, registros: int) -> dict[str, object]:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    ejecucion = next((padre for padre in ruta.parents if padre.name.startswith("NOR_")), None)
    archivo_relativo = (
        str(ruta.relative_to(ejecucion))
        if ejecucion
        else str(Path("salidas") / ruta.name)
    )
    return {
        "tipo": tipo,
        "archivo": archivo_relativo,
        "registros": registros,
        "bytes": ruta.stat().st_size,
        "sha256": digest.hexdigest(),
    }
