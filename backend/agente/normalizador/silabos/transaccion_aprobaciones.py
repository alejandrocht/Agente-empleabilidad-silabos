"""Atomic mutation of the curricular approval checkpoint.

This module owns the HITL write transaction. Its caller supplies facade-owned
adapters so legacy patch seams remain outside this cycle-free implementation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.silabos import persistencia_aprobaciones as _persistencia
from agente.normalizador.silabos import post_hitl_aprobaciones as _post_hitl
from agente.normalizador.silabos import validacion_aprobaciones as _validacion
from agente.normalizador.silabos.clasificacion import (
    clasificar_propuestas,
    estado_clasificacion,
    requiere_resolucion_curricular,
)
from agente.normalizador.silabos.paquetes import (
    PACKAGE_ID_FIELD,
    IdentidadFuenteIncompleta,
    ensamblar_paquetes_chh,
    identidad_fuente_chh,
    preparar_fila_paquete,
    revision_paquetes_chh,
)
from agente.normalizador.silabos.politica_curricular import (
    MOTIVO_COMPETENCIA_GENERICA,
    es_competencia_generica,
)

PENDIENTES_ARCHIVO = "pendientes_curriculares.jsonl"
DECISIONES_ARCHIVO = "decisiones_curriculares.jsonl"
DESCARTES_ARCHIVO = "descartes_paquetes_curriculares.jsonl"
ESTADOS_APROBACION = {"limpiado", "limpiado_con_advertencias"}
_ID_EJECUCION = re.compile(r"NOR_[0-9a-f]{16}")


def aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
    catalog_root: Callable[[], Path],
    approval_summary: Callable[..., dict[str, object]],
    hooks: Mapping[str, Any],
) -> dict[str, object]:
    """Apply a legacy-row or complete-package decision transactionally."""

    directorio = hooks.get("_validar_directorio", _validar_directorio)(directorio_ejecucion)
    rutas_transaccionales = hooks.get("_rutas_transaccionales", _rutas_transaccionales)
    roots = (
        rutas_transaccionales(directorio)
        if "_rutas_transaccionales" in hooks
        else rutas_transaccionales(directorio, catalog_root=catalog_root)
    )
    snapshot = hooks.get("_capturar_arboles", _capturar_arboles)(roots)
    try:
        return _aplicar_decisiones_curriculares(
            directorio,
            decisiones,
            actor=actor,
            revision=revision,
            catalog_root=catalog_root,
            approval_summary=approval_summary,
            hooks=hooks,
        )
    except Exception:
        hooks.get("_restaurar_arboles", _restaurar_arboles)(roots, snapshot)
        raise


def _aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
    catalog_root: Callable[[], Path],
    approval_summary: Callable[..., dict[str, object]],
    hooks: Mapping[str, Any],
) -> dict[str, object]:
    """Apply idempotent decisions and materialize the curricular profile."""

    directorio = hooks.get("_validar_directorio", _validar_directorio)(directorio_ejecucion)
    actor_normalizado = _persistencia._texto(actor)[:200] or "ejecutor"
    solicitudes = _validacion._validar_solicitudes(decisiones)
    lock = hooks["_LOCK"]
    with lock:
        manifest = hooks.get("_leer_manifest", _leer_manifest)(directorio)
        estado = _persistencia._texto(manifest.get("estado"))
        if estado not in ESTADOS_APROBACION:
            raise _validacion.AprobacionNoPermitida(
                "La aprobación solo está disponible cuando la ejecución ha terminado "
                f"correctamente; estado actual: {estado or 'desconocido'}."
            )

        reportes = directorio / "salidas" / "reportes"
        reportes.mkdir(parents=True, exist_ok=True)
        pendientes = hooks.get("_filas_clasificadas", _filas_clasificadas)(directorio)
        paquetes_actuales = hooks.get("_paquetes", _paquetes)(directorio, pendientes)
        revision_actual = revision_paquetes_chh(paquetes_actuales)
        if revision and revision != revision_actual:
            raise _validacion.RevisionCurricularInvalida(
                "La cola de paquetes cambió; recarga la revisión curricular antes de decidir."
            )
        solicitudes = _validacion._expandir_decisiones_de_paquete(solicitudes, pendientes)
        por_id = {str(fila.get("id_pendiente")): fila for fila in pendientes}
        decisiones_previas = hooks.get("_leer_decisiones", _leer_decisiones)(
            reportes / DECISIONES_ARCHIVO
        )
        descartes_previos = hooks.get("_leer_descartes", _leer_descartes)(
            reportes / DESCARTES_ARCHIVO
        )

        for solicitud in solicitudes:
            id_pendiente = solicitud["id_pendiente"]
            decision = solicitud["decision"]
            if id_pendiente not in por_id:
                raise _validacion.DecisionCurricularInvalida(
                    f"No existe el pendiente {id_pendiente!r} en esta ejecución."
                )
            if por_id[id_pendiente].get("package_identity_error"):
                raise _validacion.DecisionCurricularInvalida(
                    _persistencia._texto(por_id[id_pendiente].get("package_identity_error"))
                    or "El pendiente no tiene una identidad de relación fuente segura."
                )
            hooks.get("_validar_alcance_pendiente", _validar_alcance_pendiente)(
                por_id[id_pendiente], manifest
            )
            if (
                estado_clasificacion(por_id[id_pendiente]).auto_deduplicated
                and decision != "DISCARD"
            ):
                representante = _persistencia._texto(
                    estado_clasificacion(por_id[id_pendiente]).representative_id
                )
                raise _validacion.DecisionCurricularInvalida(
                    f"El pendiente {id_pendiente!r} fue deduplicado automáticamente; "
                    f"decida únicamente su representante {representante or 'determinista'}."
                )
            previa = decisiones_previas.get(id_pendiente)
            actual = _persistencia._texto(por_id[id_pendiente].get("decision"))
            if previa is not None or actual:
                decision_previa = _persistencia._texto(
                    (previa or por_id[id_pendiente]).get("decision")
                )
                if decision_previa != decision:
                    raise _validacion.DecisionCurricularInvalida(
                        f"El pendiente {id_pendiente!r} ya tiene una decisión distinta."
                    )

        ahora = datetime.now(UTC).isoformat()
        filas_aceptadas = 0
        filas_mantenidas = 0
        filas_descartadas = 0
        nuevas_decisiones: list[dict[str, object]] = []
        nuevos_descartes: list[dict[str, object]] = []
        candidatos = hooks.get("_cargar_candidatos", _cargar_candidatos)(reportes)
        cargar_archivos = hooks.get("_cargar_archivos_curriculares", _cargar_archivos_curriculares)
        archivos = candidatos or cargar_archivos(directorio / "salidas")
        fuentes = hooks.get("_cargar_fuentes", _cargar_fuentes)(reportes)
        relaciones = _persistencia._fusionar_relaciones(
            hooks.get("_cargar_relaciones", _cargar_relaciones)(directorio / "salidas", reportes),
            archivos["cobertura_curricular.csv"],
        )
        _validacion._validar_precondiciones_promocion(solicitudes, por_id, archivos, fuentes)

        for solicitud in solicitudes:
            id_pendiente = solicitud["id_pendiente"]
            decision = solicitud["decision"]
            fila = por_id[id_pendiente]
            if id_pendiente in decisiones_previas or _persistencia._texto(fila.get("decision")):
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
                        PACKAGE_ID_FIELD: _persistencia._texto(fila.get(PACKAGE_ID_FIELD)),
                        "package_id": _persistencia._texto(fila.get(PACKAGE_ID_FIELD)),
                        "source_identity": fila.get("source_identity", {}),
                        "package_decision": decision,
                        "decision": decision,
                        "actor": actor_normalizado,
                        "decidido_en": ahora,
                        "tipo": _persistencia._texto(fila.get("tipo")),
                        "evidencia": _evidencia(fila),
                    }
                )
                continue

            propuesta = fila.get("propuesta")
            if not isinstance(propuesta, dict):
                raise _validacion.DecisionCurricularInvalida(
                    f"El pendiente {id_pendiente!r} no tiene una propuesta estructurada."
                )
            nombre = _persistencia._texto(propuesta.get("nombre") or propuesta.get("id"))
            if not nombre:
                raise _validacion.DecisionCurricularInvalida(
                    f"El pendiente {id_pendiente!r} no tiene nombre canónico."
                )

            id_canonico = ""
            if decision == "ADD":
                id_canonico = hooks.get("_promover", _promover)(
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
            nuevas_decisiones.append(
                {
                    "id_pendiente": id_pendiente,
                    PACKAGE_ID_FIELD: _persistencia._texto(fila.get(PACKAGE_ID_FIELD)),
                    "package_id": _persistencia._texto(fila.get(PACKAGE_ID_FIELD)),
                    "source_identity": fila.get("source_identity", {}),
                    "package_decision": decision,
                    "decision": decision,
                    "actor": actor_normalizado,
                    "decidido_en": ahora,
                    "id_canonico": id_canonico or None,
                    "tipo": _persistencia._texto(fila.get("tipo")),
                    "evidencia": _evidencia(fila),
                }
            )

        paquetes_descartados_en_solicitud: set[str] = set()
        for solicitud in solicitudes:
            if solicitud["decision"] != "DISCARD":
                continue
            package_id = _persistencia._texto(solicitud.get(PACKAGE_ID_FIELD))
            if (
                package_id
                and package_id not in descartes_previos
                and package_id not in paquetes_descartados_en_solicitud
            ):
                paquetes_descartados_en_solicitud.add(package_id)
                filas_paquete = [
                    fila
                    for fila in pendientes
                    if _persistencia._texto(fila.get(PACKAGE_ID_FIELD)) == package_id
                ]
                nuevos_descartes.append(
                    hooks.get("_auditoria_descarte_paquete", _auditoria_descarte_paquete)(
                        package_id,
                        filas_paquete,
                        manifest,
                        actor_normalizado,
                        ahora,
                        _persistencia._texto(solicitud.get("reason")),
                    )
                )
        hooks.get("_retirar_relaciones_descartadas", _retirar_relaciones_descartadas)(
            relaciones, fuentes, nuevos_descartes
        )

        archivos["cobertura_curricular.csv"] = relaciones
        todas_decididas = not any(requiere_resolucion_curricular(fila) for fila in pendientes)
        hooks.get("_escribir_fuentes", _escribir_fuentes)(reportes, fuentes)
        hooks.get("_escribir_relaciones", _escribir_relaciones)(
            directorio / "salidas", reportes, relaciones
        )
        hooks.get("_escribir_jsonl_atomico", _persistencia._escribir_jsonl_atomico)(
            reportes / PENDIENTES_ARCHIVO, pendientes
        )
        hooks.get("_escribir_candidatos", _persistencia._escribir_candidatos)(
            reportes,
            archivos,
            materialized=False,
            paquetes=hooks.get("_paquetes", _paquetes)(directorio, pendientes),
        )
        gate = hooks.get("_recalcular_release_gate", _recalcular_release_gate)(
            reportes,
            archivos,
            fuentes,
            pendientes,
            materialized=False,
        )
        if todas_decididas and hooks.get(
            "_estado_estructural_materializable", _post_hitl._estado_estructural_materializable
        )(gate):
            escribir_archivos = hooks.get(
                "_escribir_archivos_curriculares", _persistencia._escribir_archivos_curriculares
            )
            escribir_archivos(directorio / "salidas", archivos)
            hooks.get("_escribir_candidatos", _persistencia._escribir_candidatos)(
                reportes,
                archivos,
                materialized=True,
                paquetes=hooks.get("_paquetes", _paquetes)(directorio, pendientes),
            )
            gate = hooks.get("_recalcular_release_gate", _recalcular_release_gate)(
                reportes,
                archivos,
                fuentes,
                pendientes,
                materialized=True,
            )
        else:
            hooks.get("_eliminar_archivos_curriculares", _eliminar_archivos_curriculares)(
                directorio / "salidas"
            )
        hooks.get("_escribir_json_atomico", _persistencia._escribir_json_atomico)(
            reportes / "release_gate.json", gate
        )
        hooks.get("_append_decisiones", _append_decisiones)(
            reportes / DECISIONES_ARCHIVO, nuevas_decisiones
        )
        hooks.get("_append_decisiones", _append_decisiones)(
            reportes / DESCARTES_ARCHIVO, nuevos_descartes
        )
        if hooks.get("_puede_materializar_perfil", _post_hitl._puede_materializar_perfil)(gate):
            materializar_perfil = hooks.get("_materializar_perfil", _materializar_perfil)
            if "_materializar_perfil" in hooks:
                materializar_perfil(directorio, manifest, archivos, reportes, pendientes, gate)
            else:
                materializar_perfil(
                    directorio,
                    manifest,
                    archivos,
                    reportes,
                    pendientes,
                    gate,
                    catalog_root=catalog_root,
                    approval_summary=approval_summary,
                )

        resumen = approval_summary(directorio)
        resumen["accepted_in_request"] = filas_aceptadas
        resumen["kept_pending_in_request"] = filas_mantenidas
        resumen["discarded_in_request"] = filas_descartadas
        resumen["release_gate"] = gate
        hooks.get("_persistir_manifest_aprobacion", _post_hitl._persistir_manifest_aprobacion)(
            directorio, manifest, archivos, gate, resumen
        )
        return {"aprobacion": resumen}


def _filas_clasificadas(directorio: Path) -> list[dict[str, object]]:
    ruta = directorio / "salidas" / "reportes" / PENDIENTES_ARCHIVO
    try:
        manifest = _leer_manifest(directorio)
    except _validacion.AprobacionNoPermitida:
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
                    carrera=_persistencia._clave_ruta(
                        _persistencia._texto(parametros.get("carrera"))
                    ),
                    periodo=_persistencia._texto(parametros.get("periodo")),
                )
            )
        except IdentidadFuenteIncompleta as exc:
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


def _rutas_transaccionales(
    directorio: Path, *, catalog_root: Callable[[], Path]
) -> tuple[Path, ...]:
    return _persistencia._rutas_transaccionales(
        directorio,
        catalog_root=catalog_root(),
        not_permitted_error=_validacion.AprobacionNoPermitida,
    )


def _capturar_arboles(roots: tuple[Path, ...]) -> dict[Path, bytes]:
    return _persistencia._capturar_arboles(
        roots, not_permitted_error=_validacion.AprobacionNoPermitida
    )


def _restaurar_arboles(roots: tuple[Path, ...], snapshot: dict[Path, bytes]) -> None:
    _persistencia._restaurar_arboles(roots, snapshot)


def _validar_directorio(directorio: Path) -> Path:
    ruta = Path(directorio)
    if ruta.is_symlink() or not _ID_EJECUCION.fullmatch(ruta.name):
        raise _validacion.AprobacionNoPermitida("Directorio de ejecución no válido.")
    try:
        resuelta = ruta.resolve(strict=True)
    except OSError as exc:
        raise _validacion.AprobacionNoPermitida("No se encontró la ejecución.") from exc
    if resuelta.is_symlink() or not (resuelta / "manifest.json").is_file():
        raise _validacion.AprobacionNoPermitida("No se encontró el manifest de la ejecución.")
    return resuelta


def _leer_manifest(directorio: Path) -> dict[str, object]:
    try:
        valor = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _validacion.AprobacionNoPermitida(
            "No se pudo leer el manifest de la ejecución."
        ) from exc
    if not isinstance(valor, dict):
        raise _validacion.AprobacionNoPermitida("El manifest de la ejecución no es válido.")
    return valor


def _validar_alcance_pendiente(fila: dict[str, object], manifest: dict[str, object]) -> None:
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera_esperada = _persistencia._clave_ruta(_persistencia._texto(parametros.get("carrera")))
    periodo_esperado = re.sub(r"[^0-9-]", "", _persistencia._texto(parametros.get("periodo")))
    if not carrera_esperada or not periodo_esperado:
        raise _validacion.AprobacionNoPermitida(
            "La ejecución no tiene carrera y periodo para validar el alcance."
        )
    carrera_fila = _persistencia._texto(fila.get("carrera"))
    periodo_fila = _persistencia._texto(fila.get("periodo"))
    if (carrera_fila or periodo_fila) and (
        _persistencia._clave_ruta(carrera_fila) != carrera_esperada
        or re.sub(r"[^0-9-]", "", periodo_fila) != periodo_esperado
    ):
        raise _validacion.DecisionCurricularInvalida(
            "El pendiente está fuera del alcance carrera/periodo de esta ejecución."
        )
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
        raise _validacion.DecisionCurricularInvalida(str(exc)) from exc
    tipo = _persistencia._texto(fila.get("tipo")).lower()
    nombre = _persistencia._texto(propuesta.get("nombre") or propuesta.get("id"))
    if tipo == "competencia" and es_competencia_generica(nombre):
        raise _validacion.DecisionCurricularInvalida(
            f"{MOTIVO_COMPETENCIA_GENERICA}: la competencia transversal no puede promoverse."
        )
    descripcion = _persistencia._texto(propuesta.get("descripcion")) or (
        f"Concepto curricular: {nombre}."
    )
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera = _persistencia._texto(parametros.get("carrera"))
    periodo = _persistencia._texto(parametros.get("periodo"))
    id_canonico = _persistencia._id_canonico(tipo, carrera, periodo, nombre)
    if tipo == "competencia":
        id_canonico = _upsert(
            archivos["catalogo_competencias.csv"],
            "nombre_competencia",
            {
                "id_competencia": id_canonico,
                "nombre_competencia": nombre,
                "descripcion_breve_competencia": descripcion,
                "tipo_competencia": _persistencia._texto(propuesta.get("tipo")) or "dura",
            },
        )
        _upsert_fuente(
            fuentes["competencias_fuente.jsonl"],
            "id_competencia_fuente",
            {
                **identidad,
                "id_competencia_fuente": _persistencia._id_canonico(
                    "COMP_SRC", carrera, periodo, str(fila.get("id_pendiente"))
                ),
                "archivo": _persistencia._texto(fila.get("archivo")),
                "nombre_competencia_fuente": nombre,
                "descripcion_fuente": _persistencia._texto(fila.get("descripcion_fuente"))
                or descripcion,
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
        _upsert_fuente(
            fuentes["habilidades_fuente.jsonl"],
            "id_habilidad_fuente",
            {
                **identidad,
                "id_habilidad_fuente": identidad["id_habilidad_fuente"],
                "archivo": _persistencia._texto(fila.get("archivo")),
                "descripcion_fuente": _persistencia._texto(fila.get("descripcion_fuente"))
                or descripcion,
                "id_habilidad_canonica": id_canonico,
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
                "metodo_resolucion": "APROBACION_EJECUTOR",
                "evidencia_fuente": _evidencia(fila),
            },
        )
    elif tipo == "herramienta":
        provenance = fila.get("evidencia_provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        origen = _persistencia._texto(provenance.get("origen"))
        seccion = _persistencia._texto(provenance.get("seccion"))
        texto_evidencia = _persistencia._texto(provenance.get("texto"))
        fuente_id = _persistencia._id_canonico(
            "HERR_SRC", carrera, periodo, str(fila.get("id_pendiente")), origen, texto_evidencia
        )
        fuente_id = _persistencia._texto(fila.get("id_herramienta_fuente")) or fuente_id
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
                "texto_evidencia": texto_evidencia or "; ".join(str(x) for x in _evidencia(fila)),
                "coincidencia": "LITERAL_PROGRAMA_ANALITICO"
                if origen == "programa_analitico"
                else "APROBACION_EJECUTOR",
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
            },
        )
    else:
        raise _validacion.DecisionCurricularInvalida(f"Tipo curricular no soportado: {tipo!r}.")
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
    try:
        identidad = identidad_fuente_chh(fila)
    except ValueError:
        return
    id_curso = identidad["id_curso"]
    id_silabo = identidad["id_silabo"]
    id_habilidad_fuente = identidad["id_habilidad_fuente"]
    id_relacion_fuente = _persistencia._texto(identidad.get("id_cob_curricular"))

    def pertenece_al_paquete(item: Mapping[str, object]) -> bool:
        return all(
            _persistencia._texto(item.get(key)) == identidad[key]
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
        if _persistencia._texto(relacion.get("id_cob_curricular")) == id_relacion_fuente
    ]
    if id_relacion_fuente and len(relaciones_fuente) != 1:
        return
    if relaciones_fuente:
        relacion_fuente = relaciones_fuente[0]
        skill_id = (
            id_canonico
            if tipo == "habilidad"
            else _persistencia._texto(relacion_fuente.get("id_habilidad_canonica"))
        )
        comp_ids = [
            id_canonico
            if tipo == "competencia"
            else _persistencia._texto(relacion_fuente.get("id_competencia_canonica"))
        ]
        tool_ids = [
            id_canonico
            if tipo == "herramienta"
            else _persistencia._texto(relacion_fuente.get("id_herramienta_canonica"))
        ]
    else:
        habilidades = {
            _persistencia._texto(item.get("id_habilidad_fuente")): _persistencia._texto(
                item.get("id_habilidad_canonica")
            )
            for item in fuentes["habilidades_fuente.jsonl"]
            if pertenece_al_paquete(item)
        }
        skill_id = id_canonico if tipo == "habilidad" else habilidades.get(id_habilidad_fuente, "")
        comp_ids = [
            _persistencia._texto(item.get("id_competencia_canonica"))
            for item in fuentes["competencias_fuente.jsonl"]
            if pertenece_al_paquete(item)
            and _persistencia._texto(item.get("id_competencia_canonica"))
        ]
        if tipo == "competencia":
            comp_ids = [id_canonico]
        tool_ids = [
            _persistencia._texto(item.get("id_herramienta_canonica"))
            for item in fuentes["herramientas_fuente.jsonl"]
            if pertenece_al_paquete(item)
            and _persistencia._texto(item.get("id_herramienta_canonica"))
        ]
        if tipo == "herramienta":
            tool_ids = [id_canonico]

    if not skill_id:
        return
    valid_comp = {
        _persistencia._texto(row.get("id_competencia"))
        for row in archivos["catalogo_competencias.csv"]
    }
    valid_skill = {
        _persistencia._texto(row.get("id_habilidad"))
        for row in archivos["catalogo_habilidades.csv"]
    }
    valid_tool = {
        _persistencia._texto(row.get("id_herramienta"))
        for row in archivos["catalogo_herramientas.csv"]
    }
    for comp_id in dict.fromkeys(comp_ids):
        if comp_id not in valid_comp or skill_id not in valid_skill:
            continue
        herramientas_finales = [tool for tool in dict.fromkeys(tool_ids) if tool in valid_tool]
        if (
            not herramientas_finales
            and relaciones_fuente
            and _persistencia._texto(relaciones_fuente[0].get("id_herramienta_fuente"))
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
                lineage=_persistencia._lineage_relacion(
                    fila, fuentes, identidad, comp_id, skill_id, tool_id
                ),
            )


def _upsert(filas: list[dict[str, str]], columna_nombre: str, fila: dict[str, str]) -> str:
    clave = clave_concepto(fila.get(columna_nombre, ""))
    for actual in filas:
        if clave_concepto(actual.get(columna_nombre, "")) == clave:
            return _persistencia._texto(
                actual.get(next(columna for columna in fila if columna.startswith("id_")))
            )
    filas.append(fila)
    return _persistencia._texto(
        next((valor for clave, valor in fila.items() if clave.startswith("id_")), "")
    )


def _upsert_fuente(
    filas: list[dict[str, object]], columna_id: str, fila: dict[str, object]
) -> None:
    identificador = _persistencia._texto(fila.get(columna_id))
    for indice, actual in enumerate(filas):
        if _persistencia._texto(actual.get(columna_id)) == identificador:
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
    if clave in {_persistencia._clave_relacion(row) for row in relaciones}:
        return
    nueva = cast(dict[str, object], _persistencia._fila_relacion(*clave))
    nueva.update(
        {clave: valor for clave, valor in (lineage or {}).items() if _persistencia._texto(valor)}
    )
    relaciones.append(nueva)


def _recalcular_release_gate(
    reportes: Path,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    pendientes: list[dict[str, object]],
    *,
    materialized: bool = True,
) -> dict[str, object]:
    return _post_hitl._recalcular_release_gate(
        reportes,
        archivos,
        fuentes,
        pendientes,
        materialized=materialized,
        invalid_error=_validacion.DecisionCurricularInvalida,
    )


def _materializar_perfil(
    directorio: Path,
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    reportes: Path,
    pendientes: list[dict[str, object]],
    gate: dict[str, object],
    *,
    catalog_root: Callable[[], Path],
    approval_summary: Callable[..., dict[str, object]],
) -> None:
    _post_hitl._materializar_perfil(
        directorio,
        manifest,
        archivos,
        reportes,
        pendientes,
        gate,
        catalog_root=catalog_root,
        approval_summary=approval_summary,
        invalid_error=_validacion.DecisionCurricularInvalida,
    )


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
            dict(_persistencia._mapping(fila.get("source_identity")))
            for fila in filas
            if _persistencia._mapping(fila.get("source_identity"))
        ),
        {},
    )
    evidencia = sorted(
        cast(Sequence[Any], {item for fila in filas for item in _evidencia(fila) if item})
    )
    propuestas = [
        {
            "tipo": _persistencia._texto(fila.get("tipo")),
            "nombre": _persistencia._texto(
                _persistencia._mapping(fila.get("propuesta")).get("nombre")
            ),
        }
        for fila in filas
    ]
    return {
        "version": "package-discard-audit/v1",
        "package_id": package_id,
        "source_identity": identidad,
        "carrera": _persistencia._clave_ruta(_persistencia._texto(parametros.get("carrera"))),
        "periodo": re.sub(r"[^0-9-]", "", _persistencia._texto(parametros.get("periodo"))),
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
    if not descartes:
        return
    descartadas = {
        _persistencia._texto(
            _persistencia._mapping(descarte.get("source_identity")).get("id_cob_curricular")
        )
        for descarte in descartes
    }
    descartadas.discard("")
    fuente_relaciones = fuentes.get("cobertura_curricular_fuente.jsonl", [])
    for fuente in fuente_relaciones:
        if _persistencia._texto(fuente.get("id_cob_curricular")) in descartadas:
            fuente["estado_resolucion"] = "DESCARTADO_POR_USUARIO"
    activas = {
        (
            _persistencia._texto(fuente.get("id_competencia_canonica")),
            _persistencia._texto(fuente.get("id_habilidad_canonica")),
            _persistencia._texto(fuente.get("id_herramienta_canonica")),
        )
        for fuente in fuente_relaciones
        if _persistencia._texto(fuente.get("estado_resolucion")) != "DESCARTADO_POR_USUARIO"
    }
    relaciones[:] = [
        relacion
        for relacion in relaciones
        if (
            _persistencia._texto(relacion.get("id_competencia")),
            _persistencia._texto(relacion.get("id_habilidad")),
            _persistencia._texto(relacion.get("id_herramienta")),
        )
        in activas
        or not fuente_relaciones
    ]


def _cargar_archivos_curriculares(salida: Path) -> dict[str, list[dict[str, str]]]:
    return _persistencia._cargar_archivos_curriculares(
        salida, invalid_error=_validacion.DecisionCurricularInvalida
    )


def _cargar_candidatos(reportes: Path) -> dict[str, list[dict[str, str]]] | None:
    return _persistencia._cargar_candidatos(
        reportes, invalid_error=_validacion.DecisionCurricularInvalida
    )


def _cargar_fuentes(reportes: Path) -> dict[str, list[dict[str, object]]]:
    return _persistencia._cargar_fuentes(
        reportes, invalid_error=_validacion.DecisionCurricularInvalida
    )


def _cargar_relaciones(salida: Path, reportes: Path) -> list[dict[str, object]]:
    return _persistencia._cargar_relaciones(
        salida, reportes, invalid_error=_validacion.DecisionCurricularInvalida
    )


def _escribir_fuentes(reportes: Path, fuentes: dict[str, list[dict[str, object]]]) -> None:
    _persistencia._escribir_fuentes(reportes, fuentes)


def _escribir_relaciones(salida: Path, reportes: Path, relaciones: list[dict[str, object]]) -> None:
    _persistencia._escribir_relaciones(
        salida, reportes, relaciones, invalid_error=_validacion.DecisionCurricularInvalida
    )


def _eliminar_archivos_curriculares(salida: Path) -> None:
    _persistencia._eliminar_archivos_curriculares(
        salida, not_permitted_error=_validacion.AprobacionNoPermitida
    )


def _leer_jsonl(ruta: Path) -> list[dict[str, object]]:
    return _persistencia._leer_jsonl(ruta, invalid_error=_validacion.DecisionCurricularInvalida)


def _leer_descartes(ruta: Path) -> dict[str, dict[str, object]]:
    return _persistencia._leer_descartes(ruta, invalid_error=_validacion.DecisionCurricularInvalida)


def _leer_decisiones(ruta: Path) -> dict[str, dict[str, object]]:
    return _persistencia._leer_decisiones(
        ruta, invalid_error=_validacion.DecisionCurricularInvalida
    )


def _append_decisiones(ruta: Path, filas: list[dict[str, object]]) -> None:
    _persistencia._append_decisiones(ruta, filas)


def _evidencia(fila: Mapping[str, object]) -> list[object]:
    evidencia: Any = fila.get("evidencia")
    return list(evidencia) if isinstance(evidencia, list) else []
