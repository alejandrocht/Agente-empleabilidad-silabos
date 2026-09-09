"""Aprobación auditable de propuestas curriculares fuera del catálogo.

Las propuestas del LLM nacen como evidencia pendiente. Este módulo es el único
seam que puede promover una de ellas al perfil de carrera/periodo. La ruta HTTP
solo valida la solicitud y delega aquí la transición, de modo que la decisión,
la proveniencia y los artefactos derivados se actualicen juntos.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from agente.normalizador.empleabilidad.catalogo import clave_concepto, ruta_catalogos
from agente.normalizador.silabos import persistencia_aprobaciones as _persistencia_aprobaciones
from agente.normalizador.silabos import presentacion_aprobaciones as _presentacion_aprobaciones
from agente.normalizador.silabos import validacion_aprobaciones as _validacion_aprobaciones
from agente.normalizador.silabos.clasificacion import (
    clasificar_propuestas,
    estado_clasificacion,
    puede_recibir_decision,
    requiere_resolucion_curricular,
    resumen_clasificacion,
)
from agente.normalizador.silabos.integridad_chh import validar_integridad_chh
from agente.normalizador.silabos.paquetes import (
    PACKAGE_ID_FIELD,
    IdentidadFuenteIncompleta,
    ensamblar_paquetes_chh,
    identidad_fuente_chh,
    preparar_fila_paquete,
    revision_paquetes_chh,
    validar_integridad_paquetes_chh,
)
from agente.normalizador.silabos.politica_curricular import (
    MOTIVO_COMPETENCIA_GENERICA,
    es_competencia_generica,
)
from agente.normalizador.silabos.salida import (
    ARCHIVOS_SALIDA,
    COBERTURA_SCHEMA,
    COMPETENCIAS_SCHEMA,
    HABILIDADES_SCHEMA,
    HERRAMIENTAS_SCHEMA,
)

AprobacionNoPermitida = _validacion_aprobaciones.AprobacionNoPermitida
DECISIONES_VALIDAS = _validacion_aprobaciones.DECISIONES_VALIDAS
DecisionCurricularInvalida = _validacion_aprobaciones.DecisionCurricularInvalida
RevisionCurricularInvalida = _validacion_aprobaciones.RevisionCurricularInvalida
_expandir_decisiones_de_paquete = _validacion_aprobaciones._expandir_decisiones_de_paquete
_validar_precondiciones_promocion = _validacion_aprobaciones._validar_precondiciones_promocion
_validar_solicitudes = _validacion_aprobaciones._validar_solicitudes

_alias_para_presentacion_api = _presentacion_aprobaciones._alias_para_presentacion_api
_campos_para_presentacion_api = _presentacion_aprobaciones._campos_para_presentacion_api
_componente_para_presentacion_api = _presentacion_aprobaciones._componente_para_presentacion_api
_fila_para_presentacion_api = _presentacion_aprobaciones._fila_para_presentacion_api
_identidad_para_presentacion_api = _presentacion_aprobaciones._identidad_para_presentacion_api
_lista_mapeos_para_presentacion_api = _presentacion_aprobaciones._lista_mapeos_para_presentacion_api
_lista_para_presentacion_api = _presentacion_aprobaciones._lista_para_presentacion_api
_paquete_para_presentacion_api = _presentacion_aprobaciones._paquete_para_presentacion_api
_pendientes_para_presentacion_api = _presentacion_aprobaciones._pendientes_para_presentacion_api
_propuesta_pendiente_para_presentacion_api = (
    _presentacion_aprobaciones._propuesta_pendiente_para_presentacion_api
)
_relacion_para_presentacion_api = _presentacion_aprobaciones._relacion_para_presentacion_api
_textos_para_presentacion_api = _presentacion_aprobaciones._textos_para_presentacion_api
_triple_canonico_para_presentacion_api = (
    _presentacion_aprobaciones._triple_canonico_para_presentacion_api
)
filas_para_presentacion_api = _presentacion_aprobaciones.filas_para_presentacion_api
paquetes_para_presentacion_api = _presentacion_aprobaciones.paquetes_para_presentacion_api

PENDIENTES_ARCHIVO = "pendientes_curriculares.jsonl"
DECISIONES_ARCHIVO = "decisiones_curriculares.jsonl"
DESCARTES_ARCHIVO = "descartes_paquetes_curriculares.jsonl"
CANDIDATOS_ARCHIVO = "candidatos_curriculares.json"
ESTADOS_PENDIENTES = {
    "PENDIENTE_CATALOGACION",
    "PENDIENTE_AMPLIACION_PERFIL",
    "REQUIERE_REVISION_HUMANA",
    "MANTENIDA_PENDIENTE",
}
ESTADOS_APROBACION = {"limpiado", "limpiado_con_advertencias"}
_ID_EJECUCION = re.compile(r"NOR_[0-9a-f]{16}")
_LOCK = RLock()


_fila_relacion = _persistencia_aprobaciones._fila_relacion
_clave_relacion = _persistencia_aprobaciones._clave_relacion
_fila_canonica_relacion = _persistencia_aprobaciones._fila_canonica_relacion
_fusionar_relaciones = _persistencia_aprobaciones._fusionar_relaciones
_preservar_relaciones_enriquecidas = _persistencia_aprobaciones._preservar_relaciones_enriquecidas
_lineage_relacion = _persistencia_aprobaciones._lineage_relacion
_escribir_archivos_curriculares = _persistencia_aprobaciones._escribir_archivos_curriculares
_escribir_candidatos = _persistencia_aprobaciones._escribir_candidatos
_escribir_fuentes = _persistencia_aprobaciones._escribir_fuentes
_escribir_csv_atomico = _persistencia_aprobaciones._escribir_csv_atomico
_escribir_jsonl_atomico = _persistencia_aprobaciones._escribir_jsonl_atomico
_escribir_json_atomico = _persistencia_aprobaciones._escribir_json_atomico
_escribir_texto_atomico = _persistencia_aprobaciones._escribir_texto_atomico
_leer_json_dict = _persistencia_aprobaciones._leer_json_dict
_id_canonico = _persistencia_aprobaciones._id_canonico
_clave_ruta = _persistencia_aprobaciones._clave_ruta
_texto = _persistencia_aprobaciones._texto
_mapping = _persistencia_aprobaciones._mapping


def _cargar_archivos_curriculares(salida: Path) -> dict[str, list[dict[str, str]]]:
    return _persistencia_aprobaciones._cargar_archivos_curriculares(
        salida, invalid_error=DecisionCurricularInvalida
    )


def _cargar_candidatos(reportes: Path) -> dict[str, list[dict[str, str]]] | None:
    return _persistencia_aprobaciones._cargar_candidatos(
        reportes, invalid_error=DecisionCurricularInvalida
    )


def _cargar_fuentes(reportes: Path) -> dict[str, list[dict[str, object]]]:
    return _persistencia_aprobaciones._cargar_fuentes(
        reportes, invalid_error=DecisionCurricularInvalida
    )


def _cargar_relaciones(salida: Path, reportes: Path) -> list[dict[str, object]]:
    return _persistencia_aprobaciones._cargar_relaciones(
        salida, reportes, invalid_error=DecisionCurricularInvalida
    )


def _eliminar_archivos_curriculares(salida: Path) -> None:
    _persistencia_aprobaciones._eliminar_archivos_curriculares(
        salida, not_permitted_error=AprobacionNoPermitida
    )


def _escribir_relaciones(
    salida: Path, reportes: Path, relaciones: list[dict[str, object]]
) -> None:
    _persistencia_aprobaciones._escribir_relaciones(
        salida,
        reportes,
        relaciones,
        invalid_error=DecisionCurricularInvalida,
    )


def _leer_jsonl(ruta: Path) -> list[dict[str, object]]:
    return _persistencia_aprobaciones._leer_jsonl(
        ruta, invalid_error=DecisionCurricularInvalida
    )


def resumen_aprobacion_curricular(
    directorio_ejecucion: Path,
    *,
    filas: list[dict[str, object]] | None = None,
    paquetes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Resume la cola sin ocultar decisiones ya registradas.

    Callers that already classified rows and assembled complete packages may
    supply those exact instances to avoid repeating the expensive work.
    """

    filas_actuales = filas if filas is not None else _filas_clasificadas(directorio_ejecucion)
    paquetes_actuales = (
        paquetes if paquetes is not None else _paquetes(directorio_ejecucion, filas_actuales)
    )
    sin_decidir = [
        fila
        for fila in filas_actuales
        if puede_recibir_decision(fila) and not _texto(fila.get("decision"))
    ]
    unresolved_records = sum(requiere_resolucion_curricular(fila) for fila in filas_actuales)
    aceptadas = [
        fila
        for fila in filas_actuales
        if not estado_clasificacion(fila).auto_deduplicated and fila.get("decision") == "ADD"
    ]
    mantenidas = [
        fila
        for fila in filas_actuales
        if not estado_clasificacion(fila).auto_deduplicated
        and fila.get("decision") == "KEEP_PENDING"
    ]
    descartadas = [
        fila
        for fila in filas_actuales
        if not estado_clasificacion(fila).auto_deduplicated and fila.get("decision") == "DISCARD"
    ]
    por_tipo: dict[str, dict[str, int]] = {}
    for fila in filas_actuales:
        tipo = _texto(fila.get("tipo")) or "otro"
        acumulado = por_tipo.setdefault(
            tipo,
            {"total": 0, "requieren_decision": 0, "accepted": 0, "remaining_pending": 0},
        )
        acumulado["total"] += 1
        if puede_recibir_decision(fila) and not _texto(fila.get("decision")):
            acumulado["requieren_decision"] += 1
        if not estado_clasificacion(fila).auto_deduplicated and fila.get("decision") == "ADD":
            acumulado["accepted"] += 1
        if requiere_resolucion_curricular(fila) or (
            not estado_clasificacion(fila).auto_deduplicated
            and fila.get("decision") == "KEEP_PENDING"
        ):
            acumulado["remaining_pending"] += 1
    clasificacion = resumen_clasificacion(filas_actuales)
    return {
        "requiere_decision": bool(sin_decidir),
        "total": len(filas_actuales),
        "pendientes_por_decidir": len(sin_decidir),
        "accepted": len(aceptadas),
        "remaining_pending": unresolved_records + len(mantenidas),
        "unresolved_records": unresolved_records,
        "decisiones_registradas": len(aceptadas) + len(mantenidas),
        "discarded": len(descartadas),
        "auto_deduplicated": sum(
            estado_clasificacion(fila).auto_deduplicated for fila in filas_actuales
        ),
        "por_tipo": por_tipo,
        "clasificacion": clasificacion,
        "paquetes": {
            "total": len(paquetes_actuales),
            "pendientes_por_decidir": sum(
                bool(paquete.get("requiere_decision")) for paquete in paquetes_actuales
            ),
            "accepted": sum(paquete.get("decision") == "ADD" for paquete in paquetes_actuales),
            "remaining_pending": sum(_paquete_pending(paquete) for paquete in paquetes_actuales),
        },
        "revision": revision_paquetes_chh(paquetes_actuales),
        "materializacion": {
            "candidatos_persistidos": (
                directorio_ejecucion / "salidas" / "reportes" / CANDIDATOS_ARCHIVO
            ).is_file(),
            "csv_canonicos_disponibles": all(
                (directorio_ejecucion / "salidas" / nombre).is_file()
                for nombre, _ in ARCHIVOS_SALIDA
            ),
        },
    }


def _paquete_pending(paquete: Mapping[str, object]) -> bool:
    """Count unresolved or explicitly retained packages, never ADD/DISCARD."""

    decision = _texto(paquete.get("decision")).upper()
    if decision in {"ADD", "DISCARD"}:
        return False
    return (
        decision == "KEEP_PENDING"
        or bool(paquete.get("requires_human_decision") or paquete.get("requiere_decision"))
        or _texto(paquete.get("decision_state")).upper() == "PENDING"
    )


def pendientes_para_revision(directorio_ejecucion: Path) -> list[dict[str, object]]:
    """Devuelve solo propuestas todavía no decididas por el ejecutor."""

    return [
        fila
        for fila in _filas_clasificadas(directorio_ejecucion)
        if puede_recibir_decision(fila) and not _texto(fila.get("decision"))
    ]


def paquetes_para_revision(directorio_ejecucion: Path) -> list[dict[str, object]]:
    """Return complete source packages while retaining aliases for audit."""

    filas = _filas_clasificadas(directorio_ejecucion)
    return [
        paquete
        for paquete in _paquetes(directorio_ejecucion, filas)
        if paquete.get("requiere_decision")
    ]


def _aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
) -> dict[str, object]:
    """Aplica decisiones idempotentes y materializa el perfil curricular.

    ``ADD`` promueve únicamente al perfil de carrera/periodo. ``KEEP_PENDING``
    deja la propuesta y su evidencia fuera de los CSV canónicos. Ambas ramas
    quedan registradas en un JSONL de decisiones para que una repetición de la
    misma petición no duplique filas ni decisiones. ``DISCARD`` is package-only
    and preserves a separate audit record while removing that package from the
    active approval projection.
    """

    directorio = _validar_directorio(directorio_ejecucion)
    actor_normalizado = _texto(actor)[:200] or "ejecutor"
    solicitudes = _validar_solicitudes(decisiones)
    with _LOCK:
        manifest = _leer_manifest(directorio)
        estado = _texto(manifest.get("estado"))
        if estado not in ESTADOS_APROBACION:
            raise AprobacionNoPermitida(
                "La aprobación solo está disponible cuando la ejecución ha terminado "
                f"correctamente; estado actual: {estado or 'desconocido'}."
            )

        reportes = directorio / "salidas" / "reportes"
        reportes.mkdir(parents=True, exist_ok=True)
        pendientes = _filas_clasificadas(directorio)
        paquetes_actuales = _paquetes(directorio, pendientes)
        revision_actual = revision_paquetes_chh(paquetes_actuales)
        if revision and revision != revision_actual:
            raise RevisionCurricularInvalida(
                "La cola de paquetes cambió; recarga la revisión curricular antes de decidir."
            )
        solicitudes = _expandir_decisiones_de_paquete(solicitudes, pendientes)
        por_id = {str(fila.get("id_pendiente")): fila for fila in pendientes}
        decisiones_previas = _leer_decisiones(reportes / DECISIONES_ARCHIVO)
        descartes_previos = _leer_descartes(reportes / DESCARTES_ARCHIVO)

        for solicitud in solicitudes:
            id_pendiente = solicitud["id_pendiente"]
            decision = solicitud["decision"]
            if id_pendiente not in por_id:
                raise DecisionCurricularInvalida(
                    f"No existe el pendiente {id_pendiente!r} en esta ejecución."
                )
            if por_id[id_pendiente].get("package_identity_error"):
                raise DecisionCurricularInvalida(
                    _texto(por_id[id_pendiente].get("package_identity_error"))
                    or "El pendiente no tiene una identidad de relación fuente segura."
                )
            _validar_alcance_pendiente(por_id[id_pendiente], manifest)
            if (
                estado_clasificacion(por_id[id_pendiente]).auto_deduplicated
                and decision != "DISCARD"
            ):
                representante = _texto(estado_clasificacion(por_id[id_pendiente]).representative_id)
                raise DecisionCurricularInvalida(
                    f"El pendiente {id_pendiente!r} fue deduplicado automáticamente; "
                    f"decida únicamente su representante {representante or 'determinista'}."
                )
            previa = decisiones_previas.get(id_pendiente)
            actual = _texto(por_id[id_pendiente].get("decision"))
            if previa is not None or actual:
                decision_previa = _texto((previa or por_id[id_pendiente]).get("decision"))
                if decision_previa != decision:
                    raise DecisionCurricularInvalida(
                        f"El pendiente {id_pendiente!r} ya tiene una decisión distinta."
                    )

        ahora = datetime.now(UTC).isoformat()
        filas_aceptadas = 0
        filas_mantenidas = 0
        filas_descartadas = 0
        nuevas_decisiones: list[dict[str, object]] = []
        nuevos_descartes: list[dict[str, object]] = []
        candidatos = _cargar_candidatos(reportes)
        archivos = candidatos or _cargar_archivos_curriculares(directorio / "salidas")
        fuentes = _cargar_fuentes(reportes)
        relaciones = _fusionar_relaciones(
            _cargar_relaciones(directorio / "salidas", reportes),
            archivos["cobertura_curricular.csv"],
        )
        _validar_precondiciones_promocion(solicitudes, por_id, archivos, fuentes)

        for solicitud in solicitudes:
            id_pendiente = solicitud["id_pendiente"]
            decision = solicitud["decision"]
            fila = por_id[id_pendiente]
            # Una repetición exacta es un no-op. Sigue participando en el
            # resumen para que el cliente reciba exactamente el mismo estado.
            if id_pendiente in decisiones_previas or _texto(fila.get("decision")):
                if decision == "ADD":
                    filas_aceptadas += 1
                elif decision == "KEEP_PENDING":
                    filas_mantenidas += 1
                else:
                    filas_descartadas += 1
                continue

            if decision == "DISCARD":
                fila["decision"] = decision
                fila["decidido_en"] = ahora
                fila["decidido_por"] = actor_normalizado
                fila["estado_resolucion"] = "DESCARTADO_POR_USUARIO"
                filas_descartadas += 1
                nuevas_decisiones.append(
                    {
                        "id_pendiente": id_pendiente,
                        PACKAGE_ID_FIELD: _texto(fila.get(PACKAGE_ID_FIELD)),
                        "package_id": _texto(fila.get(PACKAGE_ID_FIELD)),
                        "source_identity": fila.get("source_identity", {}),
                        "package_decision": decision,
                        "decision": decision,
                        "actor": actor_normalizado,
                        "decidido_en": ahora,
                        "tipo": _texto(fila.get("tipo")),
                        "evidencia": _evidencia(fila),
                    }
                )
                continue

            propuesta = fila.get("propuesta")
            if not isinstance(propuesta, dict):
                raise DecisionCurricularInvalida(
                    f"El pendiente {id_pendiente!r} no tiene una propuesta estructurada."
                )
            nombre = _texto(propuesta.get("nombre") or propuesta.get("id"))
            if not nombre:
                raise DecisionCurricularInvalida(
                    f"El pendiente {id_pendiente!r} no tiene nombre canónico."
                )

            id_canonico = ""
            if decision == "ADD":
                id_canonico = _promover(
                    fila,
                    propuesta,
                    manifest,
                    archivos,
                    fuentes,
                    relaciones,
                )
                filas_aceptadas += 1
            else:
                filas_mantenidas += 1

            fila["decision"] = decision
            fila["decidido_en"] = ahora
            fila["decidido_por"] = actor_normalizado
            fila["estado_resolucion"] = (
                "ACEPTADA_POR_USUARIO" if decision == "ADD" else "MANTENIDA_PENDIENTE"
            )
            if id_canonico:
                fila["id_canonico"] = id_canonico
            nueva: dict[str, object] = {
                "id_pendiente": id_pendiente,
                PACKAGE_ID_FIELD: _texto(fila.get(PACKAGE_ID_FIELD)),
                "package_id": _texto(fila.get(PACKAGE_ID_FIELD)),
                "source_identity": fila.get("source_identity", {}),
                "package_decision": decision,
                "decision": decision,
                "actor": actor_normalizado,
                "decidido_en": ahora,
                "id_canonico": id_canonico or None,
                "tipo": _texto(fila.get("tipo")),
                "evidencia": _evidencia(fila),
            }
            nuevas_decisiones.append(nueva)

        paquetes_descartados_en_solicitud: set[str] = set()
        for solicitud in solicitudes:
            if solicitud["decision"] != "DISCARD":
                continue
            package_id = _texto(solicitud.get(PACKAGE_ID_FIELD))
            if (
                package_id
                and package_id not in descartes_previos
                and package_id not in paquetes_descartados_en_solicitud
            ):
                paquetes_descartados_en_solicitud.add(package_id)
                filas_paquete = [
                    fila for fila in pendientes if _texto(fila.get(PACKAGE_ID_FIELD)) == package_id
                ]
                nuevos_descartes.append(
                    _auditoria_descarte_paquete(
                        package_id,
                        filas_paquete,
                        manifest,
                        actor_normalizado,
                        ahora,
                        _texto(solicitud.get("reason")),
                    )
                )
        _retirar_relaciones_descartadas(relaciones, fuentes, nuevos_descartes)

        # ``relaciones`` is intentionally a mutable working copy so an ADD can
        # append edges in any request order. Publish that final copy back into
        # the candidate package before writing CSVs; otherwise the provenance
        # JSONL would contain edges that the canonical coverage CSV omitted.
        archivos["cobertura_curricular.csv"] = relaciones
        todas_decididas = not any(requiere_resolucion_curricular(fila) for fila in pendientes)
        _escribir_fuentes(reportes, fuentes)
        _escribir_relaciones(directorio / "salidas", reportes, relaciones)
        _escribir_jsonl_atomico(reportes / PENDIENTES_ARCHIVO, pendientes)
        _escribir_candidatos(
            reportes,
            archivos,
            materialized=False,
            paquetes=_paquetes(directorio, pendientes),
        )
        gate = _recalcular_release_gate(
            reportes,
            archivos,
            fuentes,
            pendientes,
            materialized=False,
        )
        if todas_decididas and _estado_estructural_materializable(gate):
            _escribir_archivos_curriculares(directorio / "salidas", archivos)
            _escribir_candidatos(
                reportes,
                archivos,
                materialized=True,
                paquetes=_paquetes(directorio, pendientes),
            )
            gate = _recalcular_release_gate(
                reportes,
                archivos,
                fuentes,
                pendientes,
                materialized=True,
            )
        else:
            # Persist candidate evidence and the blocking gate, never a
            # canonical projection, when the final structure is unsafe.
            _eliminar_archivos_curriculares(directorio / "salidas")
        _escribir_json_atomico(reportes / "release_gate.json", gate)
        _append_decisiones(reportes / DECISIONES_ARCHIVO, nuevas_decisiones)
        _append_decisiones(reportes / DESCARTES_ARCHIVO, nuevos_descartes)
        if _puede_materializar_perfil(gate):
            _materializar_perfil(directorio, manifest, archivos, reportes, pendientes, gate)

        resumen = resumen_aprobacion_curricular(directorio)
        resumen["accepted_in_request"] = filas_aceptadas
        resumen["kept_pending_in_request"] = filas_mantenidas
        resumen["discarded_in_request"] = filas_descartadas
        resumen["release_gate"] = gate
        _persistir_manifest_aprobacion(directorio, manifest, archivos, gate, resumen)
        return {"aprobacion": resumen}


def aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
) -> dict[str, object]:
    """Apply a legacy-row or complete-package decision transactionally."""

    directorio = _validar_directorio(directorio_ejecucion)
    roots = _rutas_transaccionales(directorio)
    snapshot = _capturar_arboles(roots)
    try:
        return _aplicar_decisiones_curriculares(
            directorio, decisiones, actor=actor, revision=revision
        )
    except Exception:
        _restaurar_arboles(roots, snapshot)
        raise


def _filas_clasificadas(directorio: Path) -> list[dict[str, object]]:
    ruta = directorio / "salidas" / "reportes" / PENDIENTES_ARCHIVO
    try:
        manifest = _leer_manifest(directorio)
    except AprobacionNoPermitida:
        manifest = {}
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    filas: list[dict[str, object]] = []
    for fila in _leer_jsonl(ruta):
        if fila.get("package_identity_error"):
            filas.append(dict(fila))
            continue
        try:
            filas.append(
                preparar_fila_paquete(
                    fila,
                    id_ejecucion=directorio.name,
                    carrera=_clave_ruta(_texto(parametros.get("carrera"))),
                    periodo=_texto(parametros.get("periodo")),
                )
            )
        except IdentidadFuenteIncompleta as exc:
            # Keep the legacy row adapter visible, but never turn an
            # incomplete row into a source package or a package decision.
            legacy = dict(fila)
            legacy["package_identity_error"] = str(exc)
            filas.append(legacy)
    return clasificar_propuestas(filas)


def _paquetes(directorio: Path, filas: list[dict[str, object]]) -> list[dict[str, object]]:
    reportes = directorio / "salidas" / "reportes"
    candidatos = _cargar_candidatos(reportes) or _cargar_archivos_curriculares(
        directorio / "salidas"
    )
    fuentes = _cargar_fuentes(reportes)
    relaciones = _cargar_relaciones(directorio / "salidas", reportes)
    package_rows = [fila for fila in filas if not fila.get("package_identity_error")]
    return ensamblar_paquetes_chh(
        package_rows,
        id_ejecucion=directorio.name,
        fuentes=fuentes,
        relaciones=relaciones,
        archivos=candidatos,
    )


def _rutas_transaccionales(directorio: Path) -> tuple[Path, ...]:
    return _persistencia_aprobaciones._rutas_transaccionales(
        directorio,
        catalog_root=ruta_catalogos(),
        not_permitted_error=AprobacionNoPermitida,
    )


def _capturar_arboles(roots: tuple[Path, ...]) -> dict[Path, bytes]:
    return _persistencia_aprobaciones._capturar_arboles(
        roots, not_permitted_error=AprobacionNoPermitida
    )


def _restaurar_arboles(roots: tuple[Path, ...], snapshot: dict[Path, bytes]) -> None:
    _persistencia_aprobaciones._restaurar_arboles(roots, snapshot)


def _validar_directorio(directorio: Path) -> Path:
    ruta = Path(directorio)
    if ruta.is_symlink() or not _ID_EJECUCION.fullmatch(ruta.name):
        raise AprobacionNoPermitida("Directorio de ejecución no válido.")
    try:
        resuelta = ruta.resolve(strict=True)
    except OSError as exc:
        raise AprobacionNoPermitida("No se encontró la ejecución.") from exc
    if resuelta.is_symlink() or not (resuelta / "manifest.json").is_file():
        raise AprobacionNoPermitida("No se encontró el manifest de la ejecución.")
    return resuelta


def _leer_manifest(directorio: Path) -> dict[str, object]:
    try:
        valor = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AprobacionNoPermitida("No se pudo leer el manifest de la ejecución.") from exc
    if not isinstance(valor, dict):
        raise AprobacionNoPermitida("El manifest de la ejecución no es válido.")
    return valor


def _validar_alcance_pendiente(
    fila: dict[str, object],
    manifest: dict[str, object],
) -> None:
    """Prevents an approval row from crossing its career/period boundary."""

    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera_esperada = _clave_ruta(_texto(parametros.get("carrera")))
    periodo_esperado = re.sub(r"[^0-9-]", "", _texto(parametros.get("periodo")))
    if not carrera_esperada or not periodo_esperado:
        raise AprobacionNoPermitida(
            "La ejecución no tiene carrera y periodo para validar el alcance."
        )

    carrera_fila = _texto(fila.get("carrera"))
    periodo_fila = _texto(fila.get("periodo"))
    if (carrera_fila or periodo_fila) and (
        _clave_ruta(carrera_fila) != carrera_esperada
        or re.sub(r"[^0-9-]", "", periodo_fila) != periodo_esperado
    ):
        raise DecisionCurricularInvalida(
            "El pendiente está fuera del alcance carrera/periodo de esta ejecución."
        )

    # Old executions did not persist these fields. Backfill them from the
    # manifest before writing the decision so their audit trail becomes scoped
    # without changing the public CSV schema.
    fila["carrera"] = carrera_esperada
    fila["periodo"] = periodo_esperado


def _promover(
    fila: dict[str, object],
    propuesta: dict[str, object],
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, object]],
) -> str:
    try:
        identidad = identidad_fuente_chh(fila)
    except ValueError as exc:
        raise DecisionCurricularInvalida(str(exc)) from exc
    tipo = _texto(fila.get("tipo")).lower()
    nombre = _texto(propuesta.get("nombre") or propuesta.get("id"))
    if tipo == "competencia" and es_competencia_generica(nombre):
        raise DecisionCurricularInvalida(
            f"{MOTIVO_COMPETENCIA_GENERICA}: la competencia transversal no puede promoverse."
        )
    descripcion = _texto(propuesta.get("descripcion")) or f"Concepto curricular: {nombre}."
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera = _texto(parametros.get("carrera"))
    periodo = _texto(parametros.get("periodo"))
    id_canonico = _id_canonico(tipo, carrera, periodo, nombre)
    if tipo == "competencia":
        id_canonico = _upsert(
            archivos["catalogo_competencias.csv"],
            "nombre_competencia",
            {
                "id_competencia": id_canonico,
                "nombre_competencia": nombre,
                "descripcion_breve_competencia": descripcion,
                "tipo_competencia": _texto(propuesta.get("tipo")) or "dura",
            },
        )
        _upsert_fuente(
            fuentes["competencias_fuente.jsonl"],
            "id_competencia_fuente",
            {
                **identidad,
                "id_competencia_fuente": _id_canonico(
                    "COMP_SRC", carrera, periodo, str(fila.get("id_pendiente"))
                ),
                "archivo": _texto(fila.get("archivo")),
                "nombre_competencia_fuente": nombre,
                "descripcion_fuente": _texto(fila.get("descripcion_fuente")) or descripcion,
                "id_competencia_canonica": id_canonico,
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
                "metodo_resolucion": "APROBACION_EJECUTOR",
                "evidencia_fuente": _evidencia(fila),
            },
        )
    elif tipo == "habilidad":
        id_canonico = _upsert(
            archivos["catalogo_habilidades.csv"],
            "nombre_habilidad",
            {
                "id_habilidad": id_canonico,
                "nombre_habilidad": nombre,
                "descripcion_breve": descripcion,
            },
        )
        id_fuente = identidad["id_habilidad_fuente"]
        _upsert_fuente(
            fuentes["habilidades_fuente.jsonl"],
            "id_habilidad_fuente",
            {
                **identidad,
                "id_habilidad_fuente": id_fuente,
                "archivo": _texto(fila.get("archivo")),
                "descripcion_fuente": _texto(fila.get("descripcion_fuente")) or descripcion,
                "id_habilidad_canonica": id_canonico,
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
                "metodo_resolucion": "APROBACION_EJECUTOR",
                "evidencia_fuente": _evidencia(fila),
            },
        )
    elif tipo == "herramienta":
        provenance = fila.get("evidencia_provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        origen = _texto(provenance.get("origen"))
        seccion = _texto(provenance.get("seccion"))
        texto_evidencia = _texto(provenance.get("texto"))
        fuente_id = _id_canonico(
            "HERR_SRC",
            carrera,
            periodo,
            str(fila.get("id_pendiente")),
            origen,
            texto_evidencia,
        )
        fuente_id = _texto(fila.get("id_herramienta_fuente")) or fuente_id
        id_canonico = _upsert(
            archivos["catalogo_herramientas.csv"],
            "nombre_herramienta",
            {
                "id_herramienta": id_canonico,
                "nombre_herramienta": nombre,
                "descripcion_breve_herramienta": descripcion,
            },
        )
        _upsert_fuente(
            fuentes["herramientas_fuente.jsonl"],
            "id_herramienta_fuente",
            {
                **identidad,
                "id_herramienta_fuente": fuente_id,
                "id_herramienta_canonica": id_canonico,
                "nombre_herramienta": nombre,
                "origen_fuente": origen or "APROBACION_EJECUTOR",
                "seccion_fuente": seccion or "APROBACION_EJECUTOR",
                "texto_evidencia": texto_evidencia
                or "; ".join(str(x) for x in _evidencia(fila)),
                "coincidencia": "LITERAL_PROGRAMA_ANALITICO"
                if origen == "programa_analitico"
                else "APROBACION_EJECUTOR",
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
            },
        )
    else:
        raise DecisionCurricularInvalida(f"Tipo curricular no soportado: {tipo!r}.")
    _añadir_relaciones_de_evidencia(fila, tipo, id_canonico, archivos, fuentes, relaciones)
    return id_canonico


def _añadir_relaciones_de_evidencia(
    fila: dict[str, object],
    tipo: str,
    id_canonico: str,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, object]],
) -> None:
    """Añade relaciones solo cuando los tres extremos son verificables."""

    try:
        identidad = identidad_fuente_chh(fila)
    except ValueError:
        return
    id_curso = identidad["id_curso"]
    id_silabo = identidad["id_silabo"]
    id_habilidad_fuente = identidad["id_habilidad_fuente"]
    id_relacion_fuente = _texto(identidad.get("id_cob_curricular"))

    def pertenece_al_paquete(item: Mapping[str, object]) -> bool:
        return all(
            _texto(item.get(key)) == identidad[key]
            for key in (
                "id_ejecucion",
                "carrera",
                "periodo",
                "id_curso",
                "id_silabo",
                "id_habilidad_fuente",
            )
        )

    relaciones_fuente = [
        relacion
        for relacion in fuentes.get("cobertura_curricular_fuente.jsonl", [])
        if _texto(relacion.get("id_cob_curricular")) == id_relacion_fuente
    ]
    if id_relacion_fuente and len(relaciones_fuente) != 1:
        return

    if relaciones_fuente:
        relacion_fuente = relaciones_fuente[0]
        skill_id = (
            id_canonico
            if tipo == "habilidad"
            else _texto(relacion_fuente.get("id_habilidad_canonica"))
        )
        comp_ids = [
            id_canonico
            if tipo == "competencia"
            else _texto(relacion_fuente.get("id_competencia_canonica"))
        ]
        tool_ids = [
            id_canonico
            if tipo == "herramienta"
            else _texto(relacion_fuente.get("id_herramienta_canonica"))
        ]
    else:
        habilidades = {
            _texto(item.get("id_habilidad_fuente")): _texto(item.get("id_habilidad_canonica"))
            for item in fuentes["habilidades_fuente.jsonl"]
            if pertenece_al_paquete(item)
        }
        skill_id = id_canonico if tipo == "habilidad" else habilidades.get(id_habilidad_fuente, "")
        comp_ids = [
            _texto(item.get("id_competencia_canonica"))
            for item in fuentes["competencias_fuente.jsonl"]
            if pertenece_al_paquete(item) and _texto(item.get("id_competencia_canonica"))
        ]
        if tipo == "competencia":
            comp_ids = [id_canonico]
        tool_ids = [
            _texto(item.get("id_herramienta_canonica"))
            for item in fuentes["herramientas_fuente.jsonl"]
            if pertenece_al_paquete(item) and _texto(item.get("id_herramienta_canonica"))
        ]
        if tipo == "herramienta":
            tool_ids = [id_canonico]

    if not skill_id:
        return
    valid_comp = {
        _texto(row.get("id_competencia")) for row in archivos["catalogo_competencias.csv"]
    }
    valid_skill = {_texto(row.get("id_habilidad")) for row in archivos["catalogo_habilidades.csv"]}
    valid_tool = {
        _texto(row.get("id_herramienta")) for row in archivos["catalogo_herramientas.csv"]
    }
    for comp_id in dict.fromkeys(comp_ids):
        if comp_id not in valid_comp or skill_id not in valid_skill:
            continue
        herramientas_finales = [tool for tool in dict.fromkeys(tool_ids) if tool in valid_tool]
        if not herramientas_finales and relaciones_fuente and _texto(
            relaciones_fuente[0].get("id_herramienta_fuente")
        ):
            continue
        if not herramientas_finales:
            herramientas_finales = [""]
        for tool_id in herramientas_finales:
            _upsert_relacion(
                relaciones,
                id_curso,
                id_silabo,
                comp_id,
                skill_id,
                tool_id,
                lineage=_lineage_relacion(fila, fuentes, identidad, comp_id, skill_id, tool_id),
            )


def _upsert(
    filas: list[dict[str, str]],
    columna_nombre: str,
    fila: dict[str, str],
) -> str:
    clave = clave_concepto(fila.get(columna_nombre, ""))
    for actual in filas:
        if clave_concepto(actual.get(columna_nombre, "")) == clave:
            return _texto(
                actual.get(next(columna for columna in fila if columna.startswith("id_")))
            )
    filas.append(fila)
    return _texto(next((valor for clave, valor in fila.items() if clave.startswith("id_")), ""))


def _upsert_fuente(
    filas: list[dict[str, object]], columna_id: str, fila: dict[str, object]
) -> None:
    identificador = _texto(fila.get(columna_id))
    for indice, actual in enumerate(filas):
        if _texto(actual.get(columna_id)) == identificador:
            fusionada = dict(actual)
            fusionada.update(
                {clave: valor for clave, valor in fila.items() if valor not in ("", None, [])}
            )
            filas[indice] = fusionada
            return
    filas.append(fila)


def _upsert_relacion(
    relaciones: list[dict[str, object]],
    id_curso: str,
    id_silabo: str,
    id_competencia: str,
    id_habilidad: str,
    id_herramienta: str,
    *,
    lineage: Mapping[str, object] | None = None,
) -> None:
    clave = (id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta)
    if clave in {_clave_relacion(row) for row in relaciones}:
        return
    nueva = _fila_relacion(*clave)
    nueva.update({clave: valor for clave, valor in (lineage or {}).items() if _texto(valor)})
    relaciones.append(nueva)


def _recalcular_release_gate(
    reportes: Path,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    pendientes: list[dict[str, object]],
    *,
    materialized: bool = True,
) -> dict[str, object]:
    ruta = reportes / "release_gate.json"
    try:
        anterior = json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}
    except (OSError, json.JSONDecodeError):
        anterior = {}
    gate = dict(anterior) if isinstance(anterior, dict) else {}
    checks = dict(gate.get("checks") or {})
    ids = {
        "missing_competencies": _ids_sin_fuente(
            archivos["catalogo_competencias.csv"],
            "id_competencia",
            fuentes["competencias_fuente.jsonl"],
            "id_competencia_canonica",
        ),
        "missing_skills": _ids_sin_fuente(
            archivos["catalogo_habilidades.csv"],
            "id_habilidad",
            fuentes["habilidades_fuente.jsonl"],
            "id_habilidad_canonica",
        ),
        "missing_tools": _ids_sin_fuente(
            archivos["catalogo_herramientas.csv"],
            "id_herramienta",
            fuentes["herramientas_fuente.jsonl"],
            "id_herramienta_canonica",
        ),
    }
    checks["provenance"] = {"ok": not any(ids.values()), **ids}
    cobertura = archivos["cobertura_curricular.csv"]
    relaciones_reportadas = _leer_jsonl(reportes / "cobertura_curricular_canonica.jsonl")
    relaciones_canonicas = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_habilidad")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in relaciones_reportadas
    }
    relaciones_csv = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_habilidad")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in cobertura
    }
    checks["canonical_relations"] = {
        "ok": relaciones_csv <= relaciones_canonicas,
        "rows": len(cobertura),
        "verified": len(relaciones_canonicas),
        "missing": sorted(relaciones_csv - relaciones_canonicas),
    }
    ids_por_tipo = {
        "id_competencia": {
            _texto(fila.get("id_competencia")) for fila in archivos["catalogo_competencias.csv"]
        },
        "id_habilidad": {
            _texto(fila.get("id_habilidad")) for fila in archivos["catalogo_habilidades.csv"]
        },
        "id_herramienta": {
            _texto(fila.get("id_herramienta")) for fila in archivos["catalogo_herramientas.csv"]
        },
    }
    referencias_faltantes = sorted(
        {
            identificador
            for fila in cobertura
            for columna, ids_validos in ids_por_tipo.items()
            if (identificador := _texto(fila.get(columna))) and identificador not in ids_validos
        }
    )
    checks["canonical_references"] = {
        "ok": not referencias_faltantes,
        "missing": referencias_faltantes,
    }
    relaciones_publicadas = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_habilidad")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in cobertura
    }
    graph_hallazgos = validar_integridad_chh(archivos, relaciones_publicadas)
    graph_errors = tuple(hallazgo for hallazgo in graph_hallazgos if hallazgo.severidad == "error")
    checks["chh_graph"] = {
        "ok": not graph_errors,
        "errors": [hallazgo.a_dict() for hallazgo in graph_errors],
    }
    filas_publicables = [
        fila
        for fila in pendientes
        if _texto(fila.get("decision")) not in {"KEEP_PENDING", "DISCARD"}
    ]
    package_hallazgos = validar_integridad_paquetes_chh(
        ensamblar_paquetes_chh(
            filas_publicables,
            id_ejecucion=reportes.parent.parent.name,
            fuentes=fuentes,
            relaciones=cobertura,
            archivos=archivos,
        )
    )
    package_errors = tuple(
        hallazgo for hallazgo in package_hallazgos if hallazgo.severidad == "error"
    )
    checks["chh_packages"] = {
        "ok": not package_errors,
        "errors": [hallazgo.a_dict() for hallazgo in package_errors],
    }
    pending_counts = Counter(
        _texto(fila.get("estado_resolucion")) or "PENDIENTE" for fila in pendientes
    )
    checks["pending_preserved"] = {
        "ok": True,
        "total": len(pendientes),
        "by_state": dict(sorted(pending_counts.items())),
    }
    accepted = sum(
        1
        for fila in pendientes
        if not estado_clasificacion(fila).auto_deduplicated and fila.get("decision") == "ADD"
    )
    kept_pending = sum(
        1
        for fila in pendientes
        if not estado_clasificacion(fila).auto_deduplicated
        and fila.get("decision") == "KEEP_PENDING"
    )
    discarded = sum(
        1
        for fila in pendientes
        if not estado_clasificacion(fila).auto_deduplicated and fila.get("decision") == "DISCARD"
    )
    undecided = sum(
        1
        for fila in pendientes
        if puede_recibir_decision(fila) and not _texto(fila.get("decision"))
    )
    unresolved = sum(requiere_resolucion_curricular(fila) for fila in pendientes)
    gate["approval"] = {
        "accepted": accepted,
        "remaining_pending": kept_pending + unresolved,
        "pending_decision": undecided,
        "unresolved_records": unresolved,
        "decisions_recorded": accepted + kept_pending,
        "discarded": discarded,
        "auto_deduplicated": sum(
            estado_clasificacion(fila).auto_deduplicated for fila in pendientes
        ),
        "canonical_materialized": materialized,
    }
    gate["checks"] = checks
    dynamic_blockers = {
        "PENDING_DECISIONS",
        "CANONICAL_MATERIALIZATION_PENDING",
        "PROVENANCE_INCOMPLETE",
        "SOURCE_COVERAGE_INCOMPLETE",
        "CANONICAL_RELATION_UNVERIFIED",
        "CANONICAL_REFERENCE_MISSING",
        "CHH_GRAPH_INVALID",
        "CHH_PACKAGE_INVALID",
        "STRUCTURAL_ERRORS_PRESENT",
        "UNRESOLVED_CURRICULAR_RECORDS",
    }
    blockers = {
        str(item) for item in gate.get("blockers", []) if item and str(item) not in dynamic_blockers
    }
    if ids and any(ids.values()):
        blockers.add("PROVENANCE_INCOMPLETE")
    else:
        blockers.discard("PROVENANCE_INCOMPLETE")
    if (
        isinstance(checks.get("source_coverage"), dict)
        and checks["source_coverage"].get("ok") is False
    ):
        blockers.add("SOURCE_COVERAGE_INCOMPLETE")
    if (
        isinstance(checks.get("structural_errors"), dict)
        and checks["structural_errors"].get("ok") is False
    ):
        blockers.add("STRUCTURAL_ERRORS_PRESENT")
    if checks["canonical_relations"]["missing"]:
        blockers.add("CANONICAL_RELATION_UNVERIFIED")
    else:
        blockers.discard("CANONICAL_RELATION_UNVERIFIED")
    if referencias_faltantes:
        blockers.add("CANONICAL_REFERENCE_MISSING")
    else:
        blockers.discard("CANONICAL_REFERENCE_MISSING")
    if graph_errors:
        blockers.add("CHH_GRAPH_INVALID")
    else:
        blockers.discard("CHH_GRAPH_INVALID")
    if package_errors:
        blockers.add("CHH_PACKAGE_INVALID")
    else:
        blockers.discard("CHH_PACKAGE_INVALID")
    checks["approval"] = {
        "ok": undecided == 0 and unresolved == 0 and materialized,
        "pending_decision": undecided,
        "unresolved_records": unresolved,
        "canonical_materialized": materialized,
    }
    if undecided:
        blockers.add("PENDING_DECISIONS")
    if unresolved:
        blockers.add("UNRESOLVED_CURRICULAR_RECORDS")
    if not materialized:
        blockers.add("CANONICAL_MATERIALIZATION_PENDING")
    gate["blockers"] = sorted(blockers)
    gate["decision"] = "ALLOW_IMPORT" if not blockers else "BLOCK_IMPORT"
    observability = dict(gate.get("observability") or {})
    observability.update(
        {
            "canonical_competencies": len(archivos["catalogo_competencias.csv"]),
            "canonical_skills": len(archivos["catalogo_habilidades.csv"]),
            "canonical_tools": len(archivos["catalogo_herramientas.csv"]),
            "canonical_relations": len(archivos["cobertura_curricular.csv"]),
            "pending_records": len(pendientes),
        }
    )
    gate["observability"] = observability
    return gate


def _ids_sin_fuente(
    filas: list[dict[str, str]],
    columna_id: str,
    fuentes: list[dict[str, object]],
    columna_fuente: str,
) -> list[str]:
    ids = {_texto(fila.get(columna_id)) for fila in filas if _texto(fila.get(columna_id))}
    auditados = {
        _texto(fila.get(columna_fuente)) for fila in fuentes if _texto(fila.get(columna_fuente))
    }
    return sorted(ids - auditados)


def _estado_estructural_materializable(gate: Mapping[str, object]) -> bool:
    """Return whether evidence is safe to publish, before any CSV is written."""

    checks = gate.get("checks")
    if not isinstance(checks, Mapping):
        return False
    requeridos = (
        "source_coverage",
        "structural_errors",
        "provenance",
        "canonical_relations",
        "canonical_references",
        "chh_graph",
        "chh_packages",
    )
    if any(
        not isinstance(checks.get(nombre), Mapping) or checks[nombre].get("ok") is False
        for nombre in requeridos
    ):
        return False
    blockers = {_texto(bloqueador) for bloqueador in gate.get("blockers", [])}
    return blockers <= {"CANONICAL_MATERIALIZATION_PENDING"}


def _puede_materializar_perfil(gate: Mapping[str, object]) -> bool:
    """Defence in depth: profile writes require the fully allowed release gate."""

    checks = gate.get("checks")
    approval = checks.get("approval") if isinstance(checks, Mapping) else None
    return (
        _texto(gate.get("decision")) == "ALLOW_IMPORT"
        and _estado_estructural_materializable(gate)
        and isinstance(approval, Mapping)
        and approval.get("ok") is True
        and not gate.get("blockers")
    )


def _materializar_perfil(
    directorio: Path,
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    reportes: Path,
    pendientes: list[dict[str, object]],
    gate: dict[str, object],
) -> None:
    if not _puede_materializar_perfil(gate):
        return
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera = _clave_ruta(_texto(parametros.get("carrera")))
    periodo = re.sub(r"[^0-9-]", "", _texto(parametros.get("periodo")))
    if not carrera or not periodo:
        raise DecisionCurricularInvalida("La ejecución no tiene carrera y periodo materializables.")
    destino = ruta_catalogos() / "carreras" / carrera / periodo
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, columnas in ARCHIVOS_SALIDA:
        actual = _leer_csv_opcional(destino / nombre, columnas)
        fusionadas = _fusionar_csv(actual, archivos[nombre], columnas)
        _escribir_csv_atomico(destino / nombre, columnas, fusionadas)
    reportes_destino = destino / "reportes"
    reportes_destino.mkdir(parents=True, exist_ok=True)
    for reporte in reportes.iterdir():
        if reporte.is_file() and reporte.suffix in {".json", ".jsonl"}:
            _escribir_texto_atomico(
                reportes_destino / reporte.name, reporte.read_text(encoding="utf-8")
            )
    conteos = {
        "competencias": len(
            _leer_csv_opcional(destino / "catalogo_competencias.csv", COMPETENCIAS_SCHEMA)
        ),
        "habilidades": len(
            _leer_csv_opcional(destino / "catalogo_habilidades.csv", HABILIDADES_SCHEMA)
        ),
        "herramientas": len(
            _leer_csv_opcional(destino / "catalogo_herramientas.csv", HERRAMIENTAS_SCHEMA)
        ),
        "cobertura": len(
            _leer_csv_opcional(destino / "cobertura_curricular.csv", COBERTURA_SCHEMA)
        ),
        "pendientes": sum(
            1
            for fila in pendientes
            if not estado_clasificacion(fila).auto_deduplicated and fila.get("decision") != "ADD"
        ),
    }
    perfil = _leer_json_dict(destino / "perfil.json")
    gate_permite_importar = _texto(gate.get("decision")) == "ALLOW_IMPORT"
    perfil.update(
        {
            "tipo": "bootstrap_silabos",
            "estado": (
                "BORRADOR_CON_PENDIENTES"
                if conteos["pendientes"] or not gate_permite_importar
                else "BORRADOR"
            ),
            "carrera": carrera,
            "periodo": periodo,
            "origen_ejecucion": directorio.name,
            "conteos": conteos,
            "pendientes_por_estado": dict(
                Counter(_texto(fila.get("estado_resolucion")) for fila in pendientes)
            ),
            "release_gate": gate,
            "aprobacion_curricular": resumen_aprobacion_curricular(directorio),
        }
    )
    _escribir_json_atomico(destino / "perfil.json", perfil)


def _persistir_manifest_aprobacion(
    directorio: Path,
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    gate: dict[str, object],
    resumen: dict[str, object],
) -> None:
    """Persiste el estado derivado para que un reinicio no pierda la decisión."""

    manifest["release_gate"] = gate
    manifest["aprobacion_curricular"] = resumen
    manifest["actualizada_en"] = datetime.now(UTC).isoformat()
    outputs = manifest.get("outputs")
    outputs = (
        [dict(item) for item in outputs if isinstance(item, dict)]
        if isinstance(outputs, list)
        else []
    )
    por_archivo = {
        _texto(item.get("archivo")): item for item in outputs if _texto(item.get("archivo"))
    }
    for nombre, filas in archivos.items():
        relativo = f"salidas/{nombre}"
        ruta = directorio / relativo
        if not ruta.is_file():
            por_archivo.pop(relativo, None)
            continue
        item = por_archivo.setdefault(
            relativo,
            {"tipo": "csv_curricular", "archivo": relativo, "registros": 0},
        )
        item["registros"] = len(filas)
        _actualizar_hash_manifest(directorio, item)
    candidatos = directorio / "salidas" / "reportes" / CANDIDATOS_ARCHIVO
    if candidatos.is_file():
        relativo_candidatos = f"salidas/reportes/{CANDIDATOS_ARCHIVO}"
        item = por_archivo.setdefault(
            relativo_candidatos,
            {
                "tipo": "candidatos_curriculares",
                "archivo": relativo_candidatos,
            },
        )
        contenido_candidatos = _leer_json_dict(candidatos)
        archivos_candidatos = contenido_candidatos.get("archivos")
        archivos_candidatos = archivos_candidatos if isinstance(archivos_candidatos, dict) else {}
        item["registros"] = sum(
            len(filas) for filas in archivos_candidatos.values() if isinstance(filas, list)
        )
        _actualizar_hash_manifest(directorio, item)
    decisiones = directorio / "salidas" / "reportes" / DECISIONES_ARCHIVO
    if decisiones.is_file():
        item = por_archivo.setdefault(
            f"salidas/reportes/{DECISIONES_ARCHIVO}",
            {
                "tipo": "decisiones_curriculares",
                "archivo": f"salidas/reportes/{DECISIONES_ARCHIVO}",
            },
        )
        item["registros"] = sum(
            1 for linea in decisiones.read_text(encoding="utf-8").splitlines() if linea.strip()
        )
        _actualizar_hash_manifest(directorio, item)
    manifest["outputs"] = list(por_archivo.values())
    limpieza = manifest.get("limpieza_silabos")
    if isinstance(limpieza, dict):
        limpieza = dict(limpieza)
        limpieza["release_gate"] = gate
        limpieza["pendientes"] = resumen.get("remaining_pending", 0)
        limpieza["competencias"] = len(archivos["catalogo_competencias.csv"])
        limpieza["habilidades"] = len(archivos["catalogo_habilidades.csv"])
        limpieza["herramientas"] = len(archivos["catalogo_herramientas.csv"])
        manifest["limpieza_silabos"] = limpieza
    _escribir_json_atomico(directorio / "manifest.json", manifest)


def _actualizar_hash_manifest(directorio: Path, item: dict[str, object]) -> None:
    archivo = _texto(item.get("archivo"))
    ruta = (directorio / archivo).resolve()
    raiz = directorio.resolve()
    if not archivo or raiz not in ruta.parents or not ruta.is_file():
        return
    item["bytes"] = ruta.stat().st_size
    item["sha256"] = hashlib.sha256(ruta.read_bytes()).hexdigest()


def _fusionar_csv(
    existentes: list[dict[str, str]],
    nuevos: list[dict[str, str]],
    columnas: tuple[str, ...],
) -> list[dict[str, str]]:
    salida = [dict(fila) for fila in existentes]
    id_columna = columnas[0]
    por_id = {_texto(fila.get(id_columna)): fila for fila in salida}
    por_nombre = {
        clave_concepto(fila.get(columna)): fila
        for fila in salida
        for columna in columnas[1:2]
        if _texto(fila.get(columna))
    }
    for fila in nuevos:
        identificador = _texto(fila.get(id_columna))
        nombre = clave_concepto(next(iter(fila.get(columna, "") for columna in columnas[1:2]), ""))
        if identificador in por_id:
            por_id[identificador].update(fila)
        elif nombre and nombre in por_nombre:
            por_nombre[nombre].update(fila)
        else:
            copia = {columna: _texto(fila.get(columna)) for columna in columnas}
            salida.append(copia)
            por_id[identificador] = copia
            if nombre:
                por_nombre[nombre] = copia
    salida.sort(
        key=lambda fila: tuple(clave_concepto(fila.get(columna, "")) for columna in columnas)
    )
    return salida


def _leer_csv_opcional(ruta: Path, columnas: tuple[str, ...]) -> list[dict[str, str]]:
    if not ruta.is_file():
        return []
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if tuple(lector.fieldnames or ()) != columnas:
            raise DecisionCurricularInvalida(
                f"El esquema de {ruta.name} no coincide con el perfil."
            )
        return [{columna: _texto(fila.get(columna)) for columna in columnas} for fila in lector]


def _auditoria_descarte_paquete(
    package_id: str,
    filas: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    actor: str,
    decidido_en: str,
    reason: str,
) -> dict[str, object]:
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, Mapping) else {}
    identidad = next(
        (
            dict(_mapping(fila.get("source_identity")))
            for fila in filas
            if _mapping(fila.get("source_identity"))
        ),
        {},
    )
    evidencia = sorted({item for fila in filas for item in _evidencia(fila) if item})
    propuestas = [
        {
            "tipo": _texto(fila.get("tipo")),
            "nombre": _texto(_mapping(fila.get("propuesta")).get("nombre")),
        }
        for fila in filas
    ]
    return {
        "version": "package-discard-audit/v1",
        "package_id": package_id,
        "source_identity": identidad,
        "carrera": _clave_ruta(_texto(parametros.get("carrera"))),
        "periodo": re.sub(r"[^0-9-]", "", _texto(parametros.get("periodo"))),
        "decidido_en": decidido_en,
        "actor": actor,
        "reason": reason,
        "evidence": evidencia,
        "propuestas": propuestas,
    }


def _retirar_relaciones_descartadas(
    relaciones: list[dict[str, object]],
    fuentes: dict[str, list[dict[str, object]]],
    descartes: Sequence[Mapping[str, object]],
) -> None:
    """Remove only triples no longer backed by another source package.

    Catalog rows are shared at career scope, so deleting them for one discarded
    package would corrupt another package.  Coverage is removed only when no
    non-discarded source relation still asserts the same triple.
    """

    if not descartes:
        return
    descartadas = {
        _texto(_mapping(descarte.get("source_identity")).get("id_cob_curricular"))
        for descarte in descartes
    }
    descartadas.discard("")
    fuente_relaciones = fuentes.get("cobertura_curricular_fuente.jsonl", [])
    for fuente in fuente_relaciones:
        if _texto(fuente.get("id_cob_curricular")) in descartadas:
            fuente["estado_resolucion"] = "DESCARTADO_POR_USUARIO"
    activas = {
        (
            _texto(fuente.get("id_competencia_canonica")),
            _texto(fuente.get("id_habilidad_canonica")),
            _texto(fuente.get("id_herramienta_canonica")),
        )
        for fuente in fuente_relaciones
        if _texto(fuente.get("estado_resolucion")) != "DESCARTADO_POR_USUARIO"
    }
    relaciones[:] = [
        relacion
        for relacion in relaciones
        if (
            _texto(relacion.get("id_competencia")),
            _texto(relacion.get("id_habilidad")),
            _texto(relacion.get("id_herramienta")),
        )
        in activas
        or not fuente_relaciones
    ]


def _leer_descartes(ruta: Path) -> dict[str, dict[str, object]]:
    return {
        _texto(fila.get("package_id")): fila
        for fila in _leer_jsonl(ruta)
        if _texto(fila.get("package_id"))
    }


def _leer_decisiones(ruta: Path) -> dict[str, dict[str, object]]:
    return {
        _texto(fila.get("id_pendiente")): fila
        for fila in _leer_jsonl(ruta)
        if _texto(fila.get("id_pendiente"))
    }


def _append_decisiones(ruta: Path, filas: list[dict[str, object]]) -> None:
    if not filas:
        return
    with ruta.open("a", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")) + "\n")
        archivo.flush()


def _evidencia(fila: dict[str, object]) -> list[object]:
    evidencia = fila.get("evidencia")
    return list(evidencia) if isinstance(evidencia, list) else []
