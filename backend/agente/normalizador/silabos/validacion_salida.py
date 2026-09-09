"""Validación determinista y exposición HITL de salidas curriculares."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos.clasificacion import (
    puede_recibir_decision,
    requiere_resolucion_curricular,
)
from agente.normalizador.silabos.integridad_chh import validar_integridad_chh
from agente.normalizador.silabos.paquetes import (
    IdentidadFuenteIncompleta,
    ensamblar_paquetes_chh,
    preparar_fila_paquete,
    validar_integridad_paquetes_chh,
)
from agente.normalizador.silabos.resolucion_curricular import (
    _declaraciones_de_registros,
    _logros,
    _texto,
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
        for (
            id_curso,
            id_silabo,
            id_competencia,
            id_habilidad,
            id_herramienta,
        ) in relaciones_canonicas
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
    hallazgos.extend(validar_integridad_chh(filas_leidas, ids_cobertura_canonica))

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
