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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, clave_concepto
from agente.normalizador.modelos import Hallazgo, ResultadoValidacionSilabos
from agente.normalizador.silabos.analista_llm import DecisionCurricular
from agente.normalizador.silabos.clasificacion import (
    puede_recibir_decision,
    requiere_resolucion_curricular,
)
from agente.normalizador.silabos.integridad_chh import validar_integridad_chh

# Historical facade exports intentionally remain available from this module.
from agente.normalizador.silabos.normalizacion_curricular import (  # noqa: F401
    normalizar_registros_curriculares,
)
from agente.normalizador.silabos.paquetes import (
    IdentidadFuenteIncompleta,
    ensamblar_paquetes_chh,
    preparar_fila_paquete,
    validar_integridad_paquetes_chh,
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

COMPETENCIAS_SCHEMA: tuple[str, ...] = (
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
)
CURSOS_SCHEMA: tuple[str, ...] = (
    "id_curso",
    "nombre_curso",
    "coordinador",
    "creditos",
    "nivel",
    "tipo_curso",
    "codigo_curso",
    "id_carrera",
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
    ("curso.csv", CURSOS_SCHEMA),
    ("catalogo_competencias.csv", COMPETENCIAS_SCHEMA),
    ("catalogo_habilidades.csv", HABILIDADES_SCHEMA),
    ("catalogo_herramientas.csv", HERRAMIENTAS_SCHEMA),
    ("cobertura_curricular.csv", COBERTURA_SCHEMA),
)

_ARCHIVOS_CURRICULARES_FINALES: frozenset[str] = frozenset(
    f"salidas/{nombre}" for nombre, _ in ARCHIVOS_SALIDA
)
_REPORTES_CURRICULARES_PRE_HITL: frozenset[str] = frozenset(
    {"release_gate.json", "extraccion_cactus.json"}
)


def _hitl_curricular_completado(release_gate: object) -> bool:
    """Determina si el paquete curricular ya puede exponerse como salida final."""

    if not isinstance(release_gate, dict) or release_gate.get("decision") != "ALLOW_IMPORT":
        return False
    checks = release_gate.get("checks")
    if not isinstance(checks, dict):
        return False
    aprobacion = checks.get("approval")
    return (
        isinstance(aprobacion, dict)
        and aprobacion.get("canonical_materialized") is True
        and aprobacion.get("pending_decision") == 0
    )


def _filtrar_outputs_curriculares(
    outputs: list[dict[str, object]],
    *,
    hitl_completado: bool,
) -> list[dict[str, object]]:
    """Expone únicamente los cinco artefactos curriculares finales tras HITL."""

    publicos: list[dict[str, object]] = []
    for output in outputs:
        archivo = output.get("archivo")
        if not isinstance(archivo, str):
            continue
        if archivo not in _ARCHIVOS_CURRICULARES_FINALES or not hitl_completado:
            continue
        publicos.append(output)
    return publicos


def _filtrar_estado_publico(datos: dict[str, object]) -> dict[str, object]:
    """Aplica el contrato HITL también a manifests recuperados tras un reinicio."""

    if datos.get("tipo") != "silabos":
        return datos
    estado = dict(datos)
    release_gate = estado.get("release_gate")
    if not isinstance(release_gate, dict):
        limpieza = estado.get("limpieza_silabos")
        if isinstance(limpieza, dict):
            release_gate = limpieza.get("release_gate")
    hitl_completado = _hitl_curricular_completado(release_gate)
    outputs = estado.get("outputs")
    if isinstance(outputs, list):
        estado["outputs"] = _filtrar_outputs_curriculares(
            [dict(output) for output in outputs if isinstance(output, dict)],
            hitl_completado=hitl_completado,
        )
    limpieza = estado.get("limpieza_silabos")
    if isinstance(limpieza, dict):
        limpieza_publica = dict(limpieza)
        outputs_limpieza = limpieza_publica.get("outputs")
        if isinstance(outputs_limpieza, list):
            limpieza_publica["outputs"] = _filtrar_outputs_curriculares(
                [dict(output) for output in outputs_limpieza if isinstance(output, dict)],
                hitl_completado=hitl_completado,
            )
        estado["limpieza_silabos"] = limpieza_publica
    return estado


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
    """Normaliza los registros extraídos y escribe las cinco tablas CSV."""

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
        habilidades=len(filas_por_archivo["catalogo_habilidades.csv"]),
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


def validar_salidas_curriculares(
    salida: Path,
    registros: list[dict[str, object]],
    filas_por_archivo: dict[str, list[dict[str, str]]],
    competencias_fuente: dict[str, dict[str, object]],
    habilidades_fuente: dict[str, dict[str, object]],
    herramientas_fuente: dict[str, dict[str, object]],
    relaciones_canonicas: set[tuple[str, str, str, str, str]],
) -> tuple[Hallazgo, ...]:
    """Actúa como juez determinista antes de publicar los cinco CSV."""

    hallazgos: list[Hallazgo] = []
    esquemas = {
        "curso.csv": CURSOS_SCHEMA,
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

    cursos_csv = filas_leidas.get("curso.csv", [])
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
    ids_cursos = _ids_unicos(
        cursos_csv,
        "id_curso",
        "CURSO_ID_DUPLICADO",
        hallazgos,
    )
    for fila in cursos_csv:
        if not _texto(fila.get("id_carrera")):
            hallazgos.append(
                Hallazgo(
                    codigo="CURSO_CARRERA_AUSENTE",
                    severidad="error",
                    mensaje="El curso no puede publicarse sin una carrera autoritativa.",
                    hoja="curso.csv",
                    campo="id_carrera",
                )
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
        if _texto(fila.get("id_curso")) not in ids_cursos:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_CURSO_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a un curso que no existe en curso.csv.",
                    hoja="cobertura_curricular.csv",
                    campo="id_curso",
                    detalle=_texto(fila.get("id_curso")),
                )
            )
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
        for id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta in (
            relaciones_canonicas
        )
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
    hallazgos.extend(
        validar_integridad_chh(
            filas_leidas,
            ids_cobertura_canonica,
        )
    )

    declaraciones = _declaraciones_de_registros(registros)
    nombres_declarados = {clave_concepto(declaracion["nombre"]) for declaracion in declaraciones}
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

    if not (salida / "reportes" / "competencias_fuente.jsonl").is_file() or (
        not competencias_fuente and declaraciones
    ):
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_FUENTE_NO_AUDITADA",
                severidad="error",
                mensaje="No se generó el reporte de competencias fuente.",
                hoja="reportes/competencias_fuente.jsonl",
            )
        )
    if not (salida / "reportes" / "habilidades_fuente.jsonl").is_file() or (
        not ids_habilidad_fuente and any(_logros(datos) for datos in _datos_registros(registros))
    ):
        hallazgos.append(
            Hallazgo(
                codigo="HABILIDAD_FUENTE_NO_AUDITADA",
                severidad="error",
                mensaje="No se generó el reporte de habilidades fuente.",
                hoja="reportes/habilidades_fuente.jsonl",
            )
        )
    ids_competencias_salida = {_texto(fila.get("id_competencia")) for fila in competencias_csv}
    ids_competencias_fuente = {
        _texto(fila.get("id_competencia_canonica"))
        for fila in competencias_fuente.values()
        if _texto(fila.get("id_competencia_canonica"))
    }
    ids_competencias_sin_proveniencia = ids_competencias_salida - ids_competencias_fuente
    if ids_competencias_sin_proveniencia:
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_CANONICA_SIN_PROVENANCE",
                severidad="warning",
                mensaje=(
                    "Una competencia canónica no tiene una fila de provenance "
                    "que explique su origen curricular."
                ),
                hoja="reportes/competencias_fuente.jsonl",
                detalle="; ".join(sorted(ids_competencias_sin_proveniencia)),
            )
        )

    ids_habilidades_salida = {_texto(fila.get("id_habilidad")) for fila in habilidades_csv}
    ids_habilidades_fuente = {
        _texto(fila.get("id_habilidad_canonica"))
        for fila in habilidades_fuente.values()
        if _texto(fila.get("id_habilidad_canonica"))
    }
    ids_habilidades_sin_proveniencia = ids_habilidades_salida - ids_habilidades_fuente
    if ids_habilidades_sin_proveniencia:
        hallazgos.append(
            Hallazgo(
                codigo="HABILIDAD_CANONICA_SIN_PROVENANCE",
                severidad="warning",
                mensaje=(
                    "Una habilidad canónica no tiene una fila de provenance "
                    "que explique su logro de origen."
                ),
                hoja="reportes/habilidades_fuente.jsonl",
                detalle="; ".join(sorted(ids_habilidades_sin_proveniencia)),
            )
        )

    ids_herramientas_salida = {_texto(fila.get("id_herramienta")) for fila in herramientas_csv}
    ids_herramientas_fuente = {
        _texto(fila.get("id_herramienta_canonica"))
        for fila in herramientas_fuente.values()
        if _texto(fila.get("id_herramienta_canonica"))
    }
    ids_herramientas_sin_proveniencia = ids_herramientas_salida - ids_herramientas_fuente
    if ids_herramientas_sin_proveniencia:
        hallazgos.append(
            Hallazgo(
                codigo="HERRAMIENTA_CANONICA_SIN_PROVENANCE",
                severidad="warning",
                mensaje=(
                    "Una herramienta canónica no tiene una fila de provenance "
                    "que explique su evidencia estructurada."
                ),
                hoja="reportes/herramientas_fuente.jsonl",
                detalle="; ".join(sorted(ids_herramientas_sin_proveniencia)),
            )
        )
    return tuple(hallazgos)


def evaluar_release_gate(
    *,
    carrera: str,
    periodo: str,
    registros: int,
    logros_fuente: int,
    filas_por_archivo: dict[str, list[dict[str, str]]],
    competencias_fuente: list[dict[str, object]],
    habilidades_fuente: list[dict[str, object]],
    herramientas_fuente: list[dict[str, object]],
    relaciones_canonicas: set[tuple[str, str, str, str, str]],
    pendientes: list[dict[str, object]],
    hallazgos: list[Hallazgo],
    canonical_materialized: bool = True,
    relaciones_fuente: Iterable[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Build the immutable decision consumed by the Neo4j importer.

    Pending curriculum is allowed in a draft package, but every canonical row
    must have source provenance before the package can be imported. This keeps
    human review selective without allowing an untraceable canonical edge.
    """

    relaciones_fuente = tuple(relaciones_fuente)
    competencias = filas_por_archivo.get("catalogo_competencias.csv", [])
    habilidades = filas_por_archivo.get("catalogo_habilidades.csv", [])
    herramientas = filas_por_archivo.get("catalogo_herramientas.csv", [])
    cobertura = filas_por_archivo.get("cobertura_curricular.csv", [])

    ids_competencias = {
        _texto(fila.get("id_competencia"))
        for fila in competencias
        if _texto(fila.get("id_competencia"))
    }
    ids_habilidades = {
        _texto(fila.get("id_habilidad")) for fila in habilidades if _texto(fila.get("id_habilidad"))
    }
    ids_herramientas = {
        _texto(fila.get("id_herramienta"))
        for fila in herramientas
        if _texto(fila.get("id_herramienta"))
    }
    provenance = {
        "missing_competencies": sorted(
            ids_competencias
            - {
                _texto(fila.get("id_competencia_canonica"))
                for fila in competencias_fuente
                if _texto(fila.get("id_competencia_canonica"))
            }
        ),
        "missing_skills": sorted(
            ids_habilidades
            - {
                _texto(fila.get("id_habilidad_canonica"))
                for fila in habilidades_fuente
                if _texto(fila.get("id_habilidad_canonica"))
            }
        ),
        "missing_tools": sorted(
            ids_herramientas
            - {
                _texto(fila.get("id_herramienta_canonica"))
                for fila in herramientas_fuente
                if _texto(fila.get("id_herramienta_canonica"))
            }
        ),
    }
    provenance_complete = not any(provenance.values())

    canonical_tuples = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_habilidad")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in cobertura
    }
    missing_relations = sorted(canonical_tuples - relaciones_canonicas)
    relation_references = sorted(
        {
            identificador
            for fila in cobertura
            for columna in ("id_competencia", "id_habilidad", "id_herramienta")
            if (identificador := _texto(fila.get(columna)))
            and identificador
            not in (
                ids_competencias
                if columna == "id_competencia"
                else ids_habilidades
                if columna == "id_habilidad"
                else ids_herramientas
            )
        }
    )
    graph_hallazgos = validar_integridad_chh(filas_por_archivo, relaciones_canonicas)
    graph_errors = tuple(hallazgo for hallazgo in graph_hallazgos if hallazgo.severidad == "error")
    package_errors: tuple[Hallazgo, ...] = ()
    package_identity_errors = 0
    package_rows: list[dict[str, object]] = []
    for pendiente in pendientes:
        if pendiente.get("package_identity_error"):
            package_identity_errors += 1
            continue
        try:
            package_rows.append(
                preparar_fila_paquete(
                    pendiente,
                    id_ejecucion=_texto(pendiente.get("id_ejecucion")),
                    carrera=carrera,
                    periodo=periodo,
                )
            )
        except IdentidadFuenteIncompleta:
            package_identity_errors += 1
    if package_identity_errors:
        package_errors = (
            Hallazgo(
                codigo="PAQUETE_IDENTIDAD_INCOMPLETA",
                severidad="error",
                mensaje="Una fila pendiente no tiene identidad completa de paquete fuente.",
                hoja="pendientes_curriculares.jsonl",
                detalle=f"filas={package_identity_errors}",
            ),
        )
    elif package_rows:
        packages = ensamblar_paquetes_chh(
            package_rows,
            carrera=carrera,
            periodo=periodo,
            fuentes={
                "competencias_fuente.jsonl": competencias_fuente,
                "habilidades_fuente.jsonl": habilidades_fuente,
                "herramientas_fuente.jsonl": herramientas_fuente,
                "cobertura_curricular_fuente.jsonl": list(relaciones_fuente),
            },
            relaciones=filas_por_archivo.get("cobertura_curricular.csv", []),
            archivos=filas_por_archivo,
        )
        package_errors = tuple(validar_integridad_paquetes_chh(packages))
    source_complete = registros > 0 and len(habilidades_fuente) >= logros_fuente
    errores_estructurales = {
        (hallazgo.codigo, hallazgo.hoja, hallazgo.fila, hallazgo.campo, hallazgo.detalle)
        for hallazgo in hallazgos
        if hallazgo.severidad == "error"
    }
    no_structural_errors = not errores_estructurales
    blockers: list[str] = []
    if not source_complete:
        blockers.append("SOURCE_COVERAGE_INCOMPLETE")
    if not provenance_complete:
        blockers.append("PROVENANCE_INCOMPLETE")
    if missing_relations:
        blockers.append("CANONICAL_RELATION_UNVERIFIED")
    if relation_references:
        blockers.append("CANONICAL_REFERENCE_MISSING")
    if graph_errors:
        blockers.append("CHH_GRAPH_INVALID")
    if package_errors:
        blockers.append("CHH_PACKAGE_INVALID")
    if not no_structural_errors:
        blockers.append("STRUCTURAL_ERRORS_PRESENT")
    pendientes_sin_decidir = sum(
        1
        for pendiente in pendientes
        if puede_recibir_decision(pendiente) and not _texto(pendiente.get("decision"))
    )
    pendientes_no_resueltos = sum(
        requiere_resolucion_curricular(pendiente) for pendiente in pendientes
    )
    if pendientes_sin_decidir:
        blockers.append("PENDING_DECISIONS")
    if pendientes_no_resueltos:
        blockers.append("UNRESOLVED_CURRICULAR_RECORDS")
    if not canonical_materialized:
        blockers.append("CANONICAL_MATERIALIZATION_PENDING")

    pendientes_por_estado: dict[str, int] = {}
    for pendiente in pendientes:
        estado = _texto(pendiente.get("estado_resolucion")) or "PENDIENTE"
        pendientes_por_estado[estado] = pendientes_por_estado.get(estado, 0) + 1

    return {
        "version": "curricular-release-gate/v1",
        "decision": "ALLOW_IMPORT" if not blockers else "BLOCK_IMPORT",
        "carrera": carrera,
        "periodo": periodo,
        "blockers": blockers,
        "checks": {
            "source_coverage": {
                "ok": source_complete,
                "records": registros,
                "logros_fuente": logros_fuente,
                "habilidades_fuente": len(habilidades_fuente),
            },
            "provenance": {
                "ok": provenance_complete,
                **provenance,
            },
            "canonical_relations": {
                "ok": not missing_relations,
                "rows": len(cobertura),
                "verified": len(relaciones_canonicas),
                "missing": missing_relations,
            },
            "canonical_references": {
                "ok": not relation_references,
                "missing": relation_references,
            },
            "chh_graph": {
                "ok": not graph_errors,
                "errors": [hallazgo.a_dict() for hallazgo in graph_errors],
            },
            "chh_packages": {
                "ok": not package_errors,
                "errors": [hallazgo.a_dict() for hallazgo in package_errors],
            },
            "structural_errors": {
                "ok": no_structural_errors,
                "count": len(errores_estructurales),
            },
            "pending_preserved": _validar_pendientes_fuente(
                habilidades_fuente=habilidades_fuente,
                relaciones_fuente=relaciones_fuente,
                pendientes=pendientes,
                logros_fuente=logros_fuente,
                habilidades_canonicas=len(habilidades),
                estados=pendientes_por_estado,
            ),
            "approval": {
                "ok": (
                    pendientes_sin_decidir == 0
                    and pendientes_no_resueltos == 0
                    and canonical_materialized
                ),
                "pending_decision": pendientes_sin_decidir,
                "unresolved_records": pendientes_no_resueltos,
                "canonical_materialized": canonical_materialized,
            },
        },
        "observability": {
            "source_records": registros,
            "source_logros": logros_fuente,
            "canonical_competencies": len(competencias),
            "canonical_skills": len(habilidades),
            "canonical_tools": len(herramientas),
            "canonical_relations": len(cobertura),
            "pending_records": len(pendientes),
        },
    }


def _validar_pendientes_fuente(
    *,
    habilidades_fuente: Sequence[Mapping[str, object]],
    relaciones_fuente: Sequence[Mapping[str, object]],
    pendientes: Sequence[Mapping[str, object]],
    logros_fuente: int,
    habilidades_canonicas: int,
    estados: Mapping[str, int],
) -> dict[str, object]:
    """Verify every source outcome is canonical or explicitly pending.

    Counting ``source outcomes - unique canonical skills`` is incorrect when
    multiple outcomes reuse one canonical skill. The source skill identity and
    its competency chain are the units that must be reconciled instead.
    """

    unresolved_source_skills: set[str] = set()
    expected = 0
    if relaciones_fuente:
        for source_skill in habilidades_fuente:
            source_id = _texto(source_skill.get("id_habilidad_fuente"))
            canonical_skill = _texto(source_skill.get("id_habilidad_canonica"))
            if not source_id:
                continue
            has_competency_chain = any(
                _texto(relation.get("id_habilidad_fuente")) == source_id
                and _texto(relation.get("id_habilidad_canonica")) == canonical_skill
                and bool(_texto(relation.get("id_competencia_canonica")))
                for relation in relaciones_fuente
            )
            if not canonical_skill or not has_competency_chain:
                unresolved_source_skills.add(source_id)
    else:
        unresolved_source_skills = {
            _texto(source_skill.get("id_habilidad_fuente"))
            for source_skill in habilidades_fuente
            if not _texto(source_skill.get("id_habilidad_canonica"))
            and _texto(source_skill.get("id_habilidad_fuente"))
        }
        if not unresolved_source_skills:
            expected = max(0, logros_fuente - habilidades_canonicas)
        else:
            expected = len(unresolved_source_skills)

    pending_source_skills = {
        _texto(pendiente.get("id_habilidad_fuente"))
        for pendiente in pendientes
        if _texto(pendiente.get("tipo")).casefold() == "habilidad"
        and _texto(pendiente.get("id_habilidad_fuente"))
    }
    missing = unresolved_source_skills - pending_source_skills
    return {
        "ok": not missing,
        "total": len(pendientes),
        "by_state": dict(estados),
        "expected_unresolved": len(unresolved_source_skills) if relaciones_fuente else expected,
        "unresolved_without_pending": len(missing),
    }


def _conteo_logros_con_descripcion(registros: list[dict[str, object]]) -> int:
    return sum(
        1
        for datos in _datos_registros(registros)
        for logro in _logros(datos)
        if _texto(logro.get("descripcion"))
    )


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
    return [datos for registro in registros if isinstance((datos := registro.get("datos")), dict)]


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
