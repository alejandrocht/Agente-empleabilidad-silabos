"""Aprobación auditable de propuestas curriculares fuera del catálogo.

Las propuestas del LLM nacen como evidencia pendiente. Este módulo es el único
seam que puede promover una de ellas al perfil de carrera/periodo. La ruta HTTP
solo valida la solicitud y delega aquí la transición, de modo que la decisión,
la proveniencia y los artefactos derivados se actualicen juntos.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import RLock

from agente.normalizador.empleabilidad.catalogo import ruta_catalogos
from agente.normalizador.silabos import clasificacion as _clasificacion
from agente.normalizador.silabos import paquetes as _paquetes_chh
from agente.normalizador.silabos import persistencia_aprobaciones as _persistencia_aprobaciones
from agente.normalizador.silabos import post_hitl_aprobaciones as _post_hitl_aprobaciones
from agente.normalizador.silabos import presentacion_aprobaciones as _presentacion_aprobaciones
from agente.normalizador.silabos import salida as _salida
from agente.normalizador.silabos import transaccion_aprobaciones as _transaccion
from agente.normalizador.silabos import validacion_aprobaciones as _validacion_aprobaciones

ARCHIVOS_SALIDA = _salida.ARCHIVOS_SALIDA
COBERTURA_SCHEMA = _salida.COBERTURA_SCHEMA
COMPETENCIAS_SCHEMA = _salida.COMPETENCIAS_SCHEMA
HABILIDADES_SCHEMA = _salida.HABILIDADES_SCHEMA
HERRAMIENTAS_SCHEMA = _salida.HERRAMIENTAS_SCHEMA

AprobacionNoPermitida = _validacion_aprobaciones.AprobacionNoPermitida
DECISIONES_VALIDAS = _validacion_aprobaciones.DECISIONES_VALIDAS
DecisionCurricularInvalida = _validacion_aprobaciones.DecisionCurricularInvalida
RevisionCurricularInvalida = _validacion_aprobaciones.RevisionCurricularInvalida
_expandir_decisiones_de_paquete = _validacion_aprobaciones._expandir_decisiones_de_paquete
_validar_precondiciones_promocion = _validacion_aprobaciones._validar_precondiciones_promocion
_validar_solicitudes = _validacion_aprobaciones._validar_solicitudes

clasificar_propuestas = _clasificacion.clasificar_propuestas
estado_clasificacion = _clasificacion.estado_clasificacion
puede_recibir_decision = _clasificacion.puede_recibir_decision
requiere_resolucion_curricular = _clasificacion.requiere_resolucion_curricular
resumen_clasificacion = _clasificacion.resumen_clasificacion

PACKAGE_ID_FIELD = _paquetes_chh.PACKAGE_ID_FIELD
IdentidadFuenteIncompleta = _paquetes_chh.IdentidadFuenteIncompleta
ensamblar_paquetes_chh = _paquetes_chh.ensamblar_paquetes_chh
identidad_fuente_chh = _paquetes_chh.identidad_fuente_chh
preparar_fila_paquete = _paquetes_chh.preparar_fila_paquete
revision_paquetes_chh = _paquetes_chh.revision_paquetes_chh

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
ESTADOS_APROBACION = {"limpiado", "limpiado_con_advertencias", "no_publicado"}
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


def _escribir_relaciones(salida: Path, reportes: Path, relaciones: list[dict[str, object]]) -> None:
    _persistencia_aprobaciones._escribir_relaciones(
        salida,
        reportes,
        relaciones,
        invalid_error=DecisionCurricularInvalida,
    )


def _leer_jsonl(ruta: Path) -> list[dict[str, object]]:
    return _persistencia_aprobaciones._leer_jsonl(ruta, invalid_error=DecisionCurricularInvalida)


def _leer_descartes(ruta: Path) -> dict[str, dict[str, object]]:
    return _persistencia_aprobaciones._leer_descartes(
        ruta, invalid_error=DecisionCurricularInvalida
    )


def _leer_decisiones(ruta: Path) -> dict[str, dict[str, object]]:
    return _persistencia_aprobaciones._leer_decisiones(
        ruta, invalid_error=DecisionCurricularInvalida
    )


def _append_decisiones(ruta: Path, filas: list[dict[str, object]]) -> None:
    _persistencia_aprobaciones._append_decisiones(ruta, filas)


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


def _hooks() -> dict[str, object]:
    """Expose facade seams to the transaction without creating an import cycle."""

    return {
        "_LOCK": _LOCK,
        "_validar_directorio": _validar_directorio,
        "_rutas_transaccionales": _rutas_transaccionales,
        "_capturar_arboles": _capturar_arboles,
        "_restaurar_arboles": _restaurar_arboles,
        "_leer_manifest": _leer_manifest,
        "_filas_clasificadas": _filas_clasificadas,
        "_paquetes": _paquetes,
        "_leer_decisiones": _leer_decisiones,
        "_leer_descartes": _leer_descartes,
        "_validar_alcance_pendiente": _validar_alcance_pendiente,
        "_cargar_candidatos": _cargar_candidatos,
        "_cargar_archivos_curriculares": _cargar_archivos_curriculares,
        "_cargar_fuentes": _cargar_fuentes,
        "_cargar_relaciones": _cargar_relaciones,
        "_promover": _promover,
        "_auditoria_descarte_paquete": _auditoria_descarte_paquete,
        "_retirar_relaciones_descartadas": _retirar_relaciones_descartadas,
        "_escribir_fuentes": _escribir_fuentes,
        "_escribir_relaciones": _escribir_relaciones,
        "_escribir_jsonl_atomico": _escribir_jsonl_atomico,
        "_escribir_candidatos": _escribir_candidatos,
        "_recalcular_release_gate": _recalcular_release_gate,
        "_estado_estructural_materializable": _estado_estructural_materializable,
        "_escribir_archivos_curriculares": _escribir_archivos_curriculares,
        "_eliminar_archivos_curriculares": _eliminar_archivos_curriculares,
        "_escribir_json_atomico": _escribir_json_atomico,
        "_append_decisiones": _append_decisiones,
        "_puede_materializar_perfil": _puede_materializar_perfil,
        "_materializar_perfil": _materializar_perfil,
        "_persistir_manifest_aprobacion": _persistir_manifest_aprobacion,
    }


def _aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
) -> dict[str, object]:
    return _transaccion._aplicar_decisiones_curriculares(
        directorio_ejecucion,
        decisiones,
        actor=actor,
        revision=revision,
        catalog_root=ruta_catalogos,
        approval_summary=resumen_aprobacion_curricular,
        hooks=_hooks(),
    )


def aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
) -> dict[str, object]:
    """Apply a legacy-row or complete-package decision transactionally."""

    return _transaccion.aplicar_decisiones_curriculares(
        directorio_ejecucion,
        decisiones,
        actor=actor,
        revision=revision,
        catalog_root=ruta_catalogos,
        approval_summary=resumen_aprobacion_curricular,
        hooks=_hooks(),
    )


def _filas_clasificadas(directorio: Path) -> list[dict[str, object]]:
    return _transaccion._filas_clasificadas(directorio)


def _paquetes(directorio: Path, filas: list[dict[str, object]]) -> list[dict[str, object]]:
    return _transaccion._paquetes(directorio, filas)


def _rutas_transaccionales(directorio: Path) -> tuple[Path, ...]:
    return _transaccion._rutas_transaccionales(directorio, catalog_root=ruta_catalogos)


def _capturar_arboles(roots: tuple[Path, ...]) -> dict[Path, bytes]:
    return _transaccion._capturar_arboles(roots)


def _restaurar_arboles(roots: tuple[Path, ...], snapshot: dict[Path, bytes]) -> None:
    _transaccion._restaurar_arboles(roots, snapshot)


def _validar_directorio(directorio: Path) -> Path:
    return _transaccion._validar_directorio(directorio)


def _leer_manifest(directorio: Path) -> dict[str, object]:
    return _transaccion._leer_manifest(directorio)


def _validar_alcance_pendiente(fila: dict[str, object], manifest: dict[str, object]) -> None:
    _transaccion._validar_alcance_pendiente(fila, manifest)


def _promover(
    fila: dict[str, object],
    propuesta: dict[str, object],
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, object]],
) -> str:
    return _transaccion._promover(fila, propuesta, manifest, archivos, fuentes, relaciones)


def _añadir_relaciones_de_evidencia(
    fila: dict[str, object],
    tipo: str,
    id_canonico: str,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, object]],
) -> None:
    _transaccion._añadir_relaciones_de_evidencia(
        fila, tipo, id_canonico, archivos, fuentes, relaciones
    )


def _upsert(filas: list[dict[str, str]], columna_nombre: str, fila: dict[str, str]) -> str:
    return _transaccion._upsert(filas, columna_nombre, fila)


def _upsert_fuente(
    filas: list[dict[str, object]], columna_id: str, fila: dict[str, object]
) -> None:
    _transaccion._upsert_fuente(filas, columna_id, fila)


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
    _transaccion._upsert_relacion(
        relaciones,
        id_curso,
        id_silabo,
        id_competencia,
        id_habilidad,
        id_herramienta,
        lineage=lineage,
    )


def _recalcular_release_gate(
    reportes: Path,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    pendientes: list[dict[str, object]],
    *,
    materialized: bool = True,
) -> dict[str, object]:
    return _transaccion._recalcular_release_gate(
        reportes, archivos, fuentes, pendientes, materialized=materialized
    )


_ids_sin_fuente = _post_hitl_aprobaciones._ids_sin_fuente
_estado_estructural_materializable = _post_hitl_aprobaciones._estado_estructural_materializable
_puede_materializar_perfil = _post_hitl_aprobaciones._puede_materializar_perfil


def _materializar_perfil(
    directorio: Path,
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    reportes: Path,
    pendientes: list[dict[str, object]],
    gate: dict[str, object],
) -> None:
    _transaccion._materializar_perfil(
        directorio,
        manifest,
        archivos,
        reportes,
        pendientes,
        gate,
        catalog_root=ruta_catalogos,
        approval_summary=resumen_aprobacion_curricular,
    )


_persistir_manifest_aprobacion = _post_hitl_aprobaciones._persistir_manifest_aprobacion
_actualizar_hash_manifest = _post_hitl_aprobaciones._actualizar_hash_manifest
_fusionar_csv = _post_hitl_aprobaciones._fusionar_csv


def _leer_csv_opcional(ruta: Path, columnas: tuple[str, ...]) -> list[dict[str, str]]:
    return _post_hitl_aprobaciones._leer_csv_opcional(
        ruta, columnas, invalid_error=DecisionCurricularInvalida
    )


def _auditoria_descarte_paquete(
    package_id: str,
    filas: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    actor: str,
    decidido_en: str,
    reason: str,
) -> dict[str, object]:
    return _transaccion._auditoria_descarte_paquete(
        package_id, filas, manifest, actor, decidido_en, reason
    )


def _retirar_relaciones_descartadas(
    relaciones: list[dict[str, object]],
    fuentes: dict[str, list[dict[str, object]]],
    descartes: Sequence[Mapping[str, object]],
) -> None:
    _transaccion._retirar_relaciones_descartadas(relaciones, fuentes, descartes)


def _evidencia(fila: Mapping[str, object]) -> list[object]:
    return _transaccion._evidencia(fila)
