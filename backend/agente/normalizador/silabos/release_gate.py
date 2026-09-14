"""Pure curricular release-gate evaluation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

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
from agente.normalizador.silabos.resolucion_curricular import _texto


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
