"""Construcción y materialización del contrato CSV curricular."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH
from agente.normalizador.modelos import Hallazgo, ResultadoValidacionSilabos
from agente.normalizador.silabos.analista_llm import DecisionCurricular
from agente.normalizador.silabos.clasificacion import requiere_resolucion_curricular
from agente.normalizador.silabos.integridad_chh import validar_integridad_chh

# Historical facade exports intentionally remain available from this module.
from agente.normalizador.silabos.normalizacion_curricular import (  # noqa: F401
    normalizar_registros_curriculares,
)
from agente.normalizador.silabos.paquetes import (
    IdentidadFuenteIncompleta,  # noqa: F401
    ensamblar_paquetes_chh,
    preparar_fila_paquete,  # noqa: F401
    validar_integridad_paquetes_chh,  # noqa: F401
)
from agente.normalizador.silabos.resolucion_curricular import (  # noqa: F401
    _ALIASES_CARRERA,
    _CARRERAS_POR_NOMBRE,
    _PALABRAS_NO_EVIDENCIA,
    ESTADO_PENDIENTE_CATALOGACION,
    ESTADO_PENDIENTE_PERFIL,
    ESTADO_REVISION_HUMANA,
    HerramientaDetectada,
    NormalizacionCurricular,
    ResolucionConcepto,
    TCompetencia,
    _archivo_origen,
    _catalogo_curricular,
    _coincidencias,
    _competencias_declaradas_por_texto,
    _competencias_para_logro,
    _competencias_por_texto,
    _concepto_decidido,
    _concepto_declarado,
    _contexto_curricular,
    _declaracion_desde_catalogo,
    _declaraciones,
    _declaraciones_de_registros,
    _error,
    _estado_resolucion_determinista,
    _evidencia_programa_analitico,
    _evidencias_herramientas,
    _evidencias_herramientas_candidatas,
    _fila_cobertura,
    _filas_curso,
    _hash_id,
    _herramientas_explicitas,
    _herramientas_llm_nuevas,
    _id_carrera,
    _id_competencia_fuente,
    _logros,
    _modalidad_curso,
    _nombre_habilidad,
    _pendientes_por_relacion_fuente,
    _propuesta_dict,
    _registrar_pendiente,
    _resolver_competencia,
    _resolver_habilidad_canonica,
    _seleccionar_competencia_por_puntaje,
    _source_ref,
    _texto,
    _tipo_competencia,
    _tokens_evidencia,
    _warning,
)
from agente.normalizador.silabos.validacion_salida import (  # noqa: F401
    _ARCHIVOS_CURRICULARES_FINALES,
    _REPORTES_CURRICULARES_PRE_HITL,
    ARCHIVOS_SALIDA,
    COBERTURA_SCHEMA,
    COMPETENCIAS_SCHEMA,
    CURSOS_SCHEMA,
    HABILIDADES_SCHEMA,
    HERRAMIENTAS_SCHEMA,
    SILABO_SCHEMA,
    _conteo_logros_con_descripcion,
    _datos_registros,
    _filtrar_estado_publico,
    _filtrar_outputs_curriculares,
    _hitl_curricular_completado,
    _ids_unicos,
    _validar_pendientes_fuente,
    evaluar_release_gate,
    validar_salidas_curriculares,
)

PENDIENTES_ARCHIVO = "pendientes_curriculares.jsonl"
CANDIDATOS_ARCHIVO = "candidatos_curriculares.json"


@dataclass(frozen=True, slots=True)
class ResultadoCatalogoCurricular:
    """Resultado del gate de los cinco CSV curriculares."""

    publicable: bool
    relaciones: int
    competencias: int
    habilidades: int
    herramientas: int
    outputs: tuple[dict[str, object], ...]
    hallazgos: tuple[Hallazgo, ...]
    cuarentena: tuple[dict[str, object], ...]
    pendientes: int = 0
    release_gate: dict[str, object] = field(default_factory=dict)


def construir_salidas_curriculares(
    registros: list[dict[str, object]],
    validacion: ResultadoValidacionSilabos,
    directorio_ejecucion: Path,
    catalogo: CatalogoCHH,
    catalogo_carrera: CatalogoCHH | None = None,
    propuestas_llm: dict[str, DecisionCurricular] | None = None,
) -> ResultadoCatalogoCurricular:
    """Normaliza los registros extraídos y escribe las tablas CSV canónicas."""

    resultado = normalizar_registros_curriculares(
        registros,
        validacion,
        directorio_ejecucion.name,
        catalogo,
        catalogo_carrera,
        propuestas_llm,
    )
    salida = directorio_ejecucion / "salidas"
    salida.mkdir(parents=True, exist_ok=True)
    reportes = salida / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    filas_por_archivo = resultado.filas_por_archivo
    competencias_fuente = resultado.competencias_fuente
    habilidades_fuente = resultado.habilidades_fuente
    herramientas_fuente = resultado.herramientas_fuente
    cobertura_fuente_lineage = resultado.cobertura_fuente_lineage
    cobertura_canonica_lineage = resultado.cobertura_canonica_lineage
    pendientes_curriculares = resultado.pendientes_curriculares
    hallazgos = list(resultado.hallazgos)
    cuarentena = list(resultado.cuarentena)
    relaciones_fuente = set(cobertura_fuente_lineage)
    relaciones_canonicas = set(cobertura_canonica_lineage)
    carrera_ejecucion = _texto(validacion.carrera).upper()
    periodo_ejecucion = _texto(validacion.periodo)
    # `silabo.csv` publica la identidad resuelta de cada sílabo junto a los
    # catálogos históricos; nunca reescribe sus filas ni sus encabezados.
    filas_por_archivo["silabo.csv"] = _filas_silabo(registros, carrera_ejecucion)
    _escribir_jsonl(reportes / "competencias_fuente.jsonl", competencias_fuente.values())
    _escribir_jsonl(reportes / "habilidades_fuente.jsonl", habilidades_fuente.values())
    _escribir_jsonl(reportes / "herramientas_fuente.jsonl", herramientas_fuente.values())
    _escribir_jsonl(
        reportes / "cobertura_curricular_fuente.jsonl",
        (cobertura_fuente_lineage[relacion] for relacion in sorted(relaciones_fuente)),
    )
    _escribir_jsonl(
        reportes / "cobertura_curricular_canonica.jsonl",
        (cobertura_canonica_lineage[relacion] for relacion in sorted(relaciones_canonicas)),
    )
    _escribir_jsonl(reportes / PENDIENTES_ARCHIVO, pendientes_curriculares)
    graph_hallazgos = validar_integridad_chh(filas_por_archivo, relaciones_canonicas)
    graph_error_codes = {
        hallazgo.codigo for hallazgo in graph_hallazgos if hallazgo.severidad == "error"
    }
    if graph_error_codes:
        hallazgos.append(
            Hallazgo(
                codigo="CHH_GRAPH_GATE_BLOCKED",
                severidad="warning",
                mensaje=(
                    "La salida conserva sus candidatos, pero el release gate bloquea "
                    "la publicación hasta completar las relaciones CHH."
                ),
                hoja="cobertura_curricular.csv",
                detalle="; ".join(sorted(graph_error_codes)),
            )
        )
    _escribir_candidatos_curriculares(
        reportes,
        filas_por_archivo,
        materialized=not any(
            requiere_resolucion_curricular(fila) for fila in pendientes_curriculares
        ),
        pendientes=pendientes_curriculares,
        id_ejecucion=directorio_ejecucion.name,
        carrera=carrera_ejecucion,
        periodo=periodo_ejecucion,
        fuentes={
            "competencias_fuente.jsonl": list(competencias_fuente.values()),
            "habilidades_fuente.jsonl": list(habilidades_fuente.values()),
            "herramientas_fuente.jsonl": list(herramientas_fuente.values()),
            "cobertura_curricular_fuente.jsonl": list(cobertura_fuente_lineage.values()),
        },
    )
    canonical_materialized = not any(
        requiere_resolucion_curricular(fila) for fila in pendientes_curriculares
    )
    if canonical_materialized:
        for nombre, columnas in ARCHIVOS_SALIDA:
            ruta = salida / nombre
            _escribir_csv(ruta, columnas, filas_por_archivo[nombre])
        hallazgos_validacion = validar_salidas_curriculares(
            salida,
            registros,
            filas_por_archivo,
            competencias_fuente,
            habilidades_fuente,
            herramientas_fuente,
            relaciones_canonicas,
        )
        # Graph failures are already represented by the dedicated release
        # check above. Keep them out of the generic extraction-error channel so
        # a candidate package remains reviewable while import stays blocked.
        hallazgos_validacion = tuple(
            hallazgo
            for hallazgo in hallazgos_validacion
            if hallazgo.codigo not in graph_error_codes
        )
    else:
        _retirar_csv_canónico(salida)
        hallazgos_validacion = ()
    hallazgos.extend(hallazgos_validacion)
    release_gate = evaluar_release_gate(
        carrera=carrera_ejecucion,
        periodo=periodo_ejecucion,
        registros=len(registros),
        logros_fuente=_conteo_logros_con_descripcion(registros),
        filas_por_archivo=filas_por_archivo,
        competencias_fuente=list(competencias_fuente.values()),
        habilidades_fuente=list(habilidades_fuente.values()),
        herramientas_fuente=list(herramientas_fuente.values()),
        relaciones_canonicas=relaciones_canonicas,
        pendientes=pendientes_curriculares,
        hallazgos=hallazgos,
        canonical_materialized=canonical_materialized,
        relaciones_fuente=list(cobertura_fuente_lineage.values()),
    )
    _escribir_json(
        reportes / "release_gate.json",
        release_gate,
    )
    # Los CSV ya escritos siguen siendo evidencia útil incluso cuando el gate
    # los marca como no publicables; declararlos permite inspeccionarlos sin
    # convertirlos en una salida aprobada.
    outputs = [
        _output(salida / nombre, "csv_curricular", len(filas_por_archivo[nombre]))
        for nombre, _ in ARCHIVOS_SALIDA
        if (salida / nombre).is_file()
    ]
    outputs.extend(
        [
            _output(
                reportes / "competencias_fuente.jsonl",
                "provenance",
                len(competencias_fuente),
            ),
            _output(
                reportes / "habilidades_fuente.jsonl",
                "provenance",
                len(habilidades_fuente),
            ),
            _output(
                reportes / "herramientas_fuente.jsonl",
                "provenance",
                len(herramientas_fuente),
            ),
            _output(
                reportes / "cobertura_curricular_fuente.jsonl",
                "provenance",
                len(relaciones_fuente),
            ),
            _output(
                reportes / "cobertura_curricular_canonica.jsonl",
                "provenance",
                len(relaciones_canonicas),
            ),
            _output(
                reportes / PENDIENTES_ARCHIVO,
                "pendientes_curriculares",
                len(pendientes_curriculares),
            ),
            _output(reportes / "release_gate.json", "release_gate", 1),
        ]
    )
    if not canonical_materialized:
        outputs.append(
            _output(
                reportes / CANDIDATOS_ARCHIVO,
                "candidatos_curriculares",
                sum(len(filas) for filas in filas_por_archivo.values()),
            )
        )
    publicable = bool(registros) and not any(
        hallazgo.severidad == "error" for hallazgo in hallazgos
    )
    return ResultadoCatalogoCurricular(
        publicable=publicable,
        relaciones=len(filas_por_archivo["cobertura_curricular.csv"]),
        competencias=len(filas_por_archivo["catalogo_competencias.csv"]),
        habilidades=len(filas_por_archivo["catalogo_logros.csv"]),
        herramientas=len(filas_por_archivo["catalogo_herramientas.csv"]),
        outputs=tuple(outputs),
        hallazgos=tuple(hallazgos),
        cuarentena=tuple(cuarentena),
        pendientes=len(pendientes_curriculares),
        release_gate=release_gate,
    )


def _escribir_jsonl(ruta: Path, filas: Iterable[object]) -> None:
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")))
            archivo.write("\n")


def _escribir_candidatos_curriculares(
    reportes: Path,
    filas_por_archivo: dict[str, list[dict[str, str]]],
    *,
    materialized: bool,
    pendientes: list[dict[str, object]] | None = None,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> None:
    """Persists canonical candidates separately from importable CSV files."""

    contenido = {
        "version": "curricular-candidates/v1",
        "materialized": materialized,
        "archivos": {nombre: list(filas_por_archivo[nombre]) for nombre, _ in ARCHIVOS_SALIDA},
        "paquetes": ensamblar_paquetes_chh(
            [fila for fila in (pendientes or []) if not fila.get("package_identity_error")],
            id_ejecucion=id_ejecucion,
            carrera=carrera,
            periodo=periodo,
            fuentes=fuentes,
            relaciones=filas_por_archivo.get("cobertura_curricular.csv", []),
            archivos=filas_por_archivo,
        ),
        "decision_policy": {
            "exact_duplicates": "AUTO_DEDUPLICATE",
            "semantic_duplicates": "REVIEW_ONLY",
            "suspicious_tools": "REVIEW_ONLY",
            "auto_delete": False,
            "auto_merge": False,
            "source_rows_preserved": True,
        },
    }
    _escribir_json(reportes / CANDIDATOS_ARCHIVO, contenido)


def _retirar_csv_canónico(salida: Path) -> None:
    """Ensures an unresolved execution cannot expose stale canonical CSVs."""

    for nombre, _ in ARCHIVOS_SALIDA:
        try:
            (salida / nombre).unlink(missing_ok=True)
        except OSError:
            # The release gate remains blocked; retaining no stale publication
            # is preferable to failing the source/provenance checkpoint.
            continue


def _filas_silabo(
    registros: list[dict[str, object]],
    carrera_ejecucion: str,
) -> list[dict[str, str]]:
    """Materializa una fila por sílabo procesado sin inventar sumilla."""

    silabos: dict[str, dict[str, str]] = {}
    for registro in registros:
        if _texto(registro.get("carrera")).upper() != carrera_ejecucion:
            continue
        datos_objeto = registro.get("datos")
        datos = datos_objeto if isinstance(datos_objeto, dict) else {}
        id_silabo = _texto(registro.get("id_silabo"))
        id_curso = _texto(registro.get("id_curso"))
        if not id_silabo or not id_curso:
            continue
        silabos.setdefault(
            id_silabo,
            {
                "id_silabo": id_silabo,
                "codigo_silabo": _texto(datos.get("codigo_curso")),
                "sumilla": _texto(datos.get("sumilla")),
                "id_curso": id_curso,
            },
        )
    return [silabos[id_silabo] for id_silabo in sorted(silabos)]


def _escribir_csv(ruta: Path, columnas: tuple[str, ...], filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="raise")
        escritor.writeheader()
        escritor.writerows(
            {columna: fila.get(columna, "") for columna in columnas} for fila in filas
        )


def _escribir_json(ruta: Path, contenido: dict[str, object]) -> None:
    ruta.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _output(ruta: Path, tipo: str, registros: int) -> dict[str, object]:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    ejecucion = next((padre for padre in ruta.parents if padre.name.startswith("NOR_")), None)
    archivo_relativo = (
        ruta.relative_to(ejecucion).as_posix()
        if ejecucion
        else (Path("salidas") / ruta.name).as_posix()
    )
    return {
        "tipo": tipo,
        "archivo": archivo_relativo,
        "registros": registros,
        "bytes": ruta.stat().st_size,
        "sha256": digest.hexdigest(),
    }
