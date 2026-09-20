"""Approval journal and materialization adapter for technical proposals."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from threading import RLock

from agente.normalizador.silabos import salida_catalogos
from agente.normalizador.silabos.salida_catalogos import construir_salidas_tecnicas

errores_tecnicos = import_module("agente.normalizador.silabos.errores_tecnicos")
AprobacionNoPermitida = errores_tecnicos.AprobacionNoPermitida
DecisionCurricularInvalida = errores_tecnicos.DecisionCurricularInvalida
RevisionCurricularInvalida = errores_tecnicos.RevisionCurricularInvalida

PROPUESTAS_ARCHIVO = "propuestas_tecnicas.jsonl"
DECISIONES_ARCHIVO = "decisiones_tecnicas.jsonl"
_ID_EJECUCION = re.compile(r"NOR_[0-9a-f]{16}")
_DECISIONES_VALIDAS = frozenset({"ADD", "DISCARD", "KEEP_PENDING"})
_ESTADOS_TERMINALES = frozenset({"limpiado", "limpiado_con_advertencias", "no_publicado"})
_LOCK = RLock()


def es_ejecucion_curricular(manifest: Mapping[str, object]) -> bool:
    return manifest.get("tipo") == "silabos"


def _validar_directorio(directorio: Path) -> Path:
    ruta = Path(directorio)
    if ruta.is_symlink() or _ID_EJECUCION.fullmatch(ruta.name) is None:
        raise AprobacionNoPermitida("Directorio de ejecución no válido.")
    try:
        resuelta = ruta.resolve(strict=True)
    except OSError as exc:
        raise AprobacionNoPermitida("No se encontró la ejecución.") from exc
    if resuelta.is_symlink() or not (resuelta / "manifest.json").is_file():
        raise AprobacionNoPermitida("No se encontró el manifest de la ejecución.")
    return resuelta


def _leer_json(ruta: Path, *, requerido: bool = False) -> dict[str, object]:
    if not ruta.is_file():
        if requerido:
            raise DecisionCurricularInvalida(f"No existe el reporte técnico {ruta.name}.")
        return {}
    try:
        valor = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionCurricularInvalida(f"Reporte JSON inválido: {ruta.name}.") from exc
    if not isinstance(valor, dict):
        raise DecisionCurricularInvalida(f"Reporte JSON inválido: {ruta.name}.")
    return valor


def _leer_jsonl(ruta: Path, *, requerido: bool = False) -> list[dict[str, object]]:
    if not ruta.is_file():
        if requerido:
            raise DecisionCurricularInvalida(f"No existe el reporte técnico {ruta.name}.")
        return []
    filas: list[dict[str, object]] = []
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise DecisionCurricularInvalida(
            f"No se pudo leer el reporte técnico {ruta.name}."
        ) from exc
    for linea in lineas:
        if not linea.strip():
            continue
        try:
            valor = json.loads(linea)
        except json.JSONDecodeError as exc:
            raise DecisionCurricularInvalida(f"Reporte JSONL inválido: {ruta.name}.") from exc
        if not isinstance(valor, dict):
            raise DecisionCurricularInvalida(f"Reporte JSONL inválido: {ruta.name}.")
        filas.append(valor)
    return filas


def _reportes(directorio: Path) -> Path:
    return directorio / "salidas" / "reportes"


def _cargar_manifest(directorio: Path) -> dict[str, object]:
    try:
        valor = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AprobacionNoPermitida("No se pudo leer el manifest de la ejecución.") from exc
    if not isinstance(valor, dict):
        raise AprobacionNoPermitida("El manifest de la ejecución no es válido.")
    return valor


def _cargar_propuestas(directorio: Path) -> list[dict[str, object]]:
    propuestas = _leer_jsonl(_reportes(directorio) / PROPUESTAS_ARCHIVO, requerido=True)
    ids: set[str] = set()
    for propuesta in propuestas:
        identificador = str(propuesta.get("id_propuesta") or "").strip()
        if not identificador:
            raise DecisionCurricularInvalida("Toda propuesta técnica debe incluir id_propuesta.")
        if identificador in ids:
            raise DecisionCurricularInvalida(
                f"La propuesta técnica {identificador!r} está duplicada."
            )
        ids.add(identificador)
    return propuestas


def _cargar_journal(directorio: Path) -> list[dict[str, object]]:
    filas = _leer_jsonl(_reportes(directorio) / DECISIONES_ARCHIVO)
    por_id: dict[str, str] = {}
    for fila in filas:
        identificador = str(fila.get("id_propuesta") or "").strip()
        decision = str(fila.get("decision") or "").strip().upper()
        if not identificador or decision not in _DECISIONES_VALIDAS:
            raise DecisionCurricularInvalida("El diario técnico contiene una decisión inválida.")
        anterior = por_id.get(identificador)
        if anterior is not None and anterior != decision:
            raise DecisionCurricularInvalida(
                f"La propuesta técnica {identificador!r} tiene decisiones contradictorias."
            )
        por_id[identificador] = decision
    return filas


def _revision(
    propuestas: Sequence[Mapping[str, object]],
    journal: Sequence[Mapping[str, object]] = (),
) -> str:
    decisiones = _decisiones_por_id(journal)
    contenido = json.dumps(
        [
            {
                "propuesta": dict(propuesta),
                "decision": str(
                    decisiones.get(str(propuesta.get("id_propuesta")), {}).get("decision") or ""
                ),
            }
            for propuesta in propuestas
        ],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"TEC_REV_{hashlib.sha256(contenido).hexdigest()[:16]}"


def _decisiones_por_id(journal: Sequence[Mapping[str, object]]) -> dict[str, Mapping[str, object]]:
    return {str(fila["id_propuesta"]): fila for fila in journal}


def _evidencia_literal(propuesta: Mapping[str, object]) -> list[str]:
    evidencia = propuesta.get("evidencia")
    if not isinstance(evidencia, Sequence) or isinstance(evidencia, (str, bytes)):
        return []
    resultado: list[str] = []
    for item in evidencia:
        if isinstance(item, Mapping):
            fragmento = str(item.get("fragmento") or "").strip()
        else:
            fragmento = str(item or "").strip()
        if fragmento:
            resultado.append(fragmento)
    return resultado


def _fila_api(
    propuesta: Mapping[str, object],
    decision: str,
) -> dict[str, object]:
    identificador = str(propuesta.get("id_propuesta") or "")
    estado = {
        "": "PENDIENTE_APROBACION",
        "ADD": "APROBADA",
        "DISCARD": "DESCARTADA",
        "KEEP_PENDING": "MANTENIDA_PENDIENTE",
    }[decision]
    evidencia = _evidencia_literal(propuesta)
    detalles = dict(propuesta)
    detalles["id"] = identificador
    detalles["tipo"] = "tecnica"
    detalles["evidencia"] = evidencia
    return {
        **dict(propuesta),
        "id_pendiente": identificador,
        "tipo": "competencia_tecnica",
        "estado_resolucion": estado,
        "decision": decision or None,
        "requiere_decision": decision in {"", "KEEP_PENDING"},
        "propuesta": detalles,
        "evidencia": evidencia,
        "evidencia_literal": evidencia,
    }


def _filas_actuales(
    propuestas: Sequence[Mapping[str, object]],
    journal: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    decisiones = _decisiones_por_id(journal)
    ids = {str(propuesta.get("id_propuesta") or "") for propuesta in propuestas}
    huérfanas = set(decisiones) - ids
    if huérfanas:
        raise DecisionCurricularInvalida(
            f"El diario técnico referencia propuestas inexistentes: {sorted(huérfanas)!r}."
        )
    return [
        _fila_api(
            propuesta,
            str(decisiones.get(str(propuesta["id_propuesta"]), {}).get("decision") or ""),
        )
        for propuesta in propuestas
    ]


def _leer_gate(directorio: Path) -> dict[str, object]:
    return _leer_json(_reportes(directorio) / "release_gate.json")


def _resumen(
    directorio: Path,
    propuestas: Sequence[Mapping[str, object]],
    journal: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    filas = _filas_actuales(propuestas, journal)
    decisiones = [str(fila.get("decision") or "") for fila in filas]
    pendientes = sum(decision in {"", "KEEP_PENDING"} for decision in decisiones)
    gate = _leer_gate(directorio)
    return {
        "requiere_decision": pendientes > 0,
        "total": len(filas),
        "pendientes_por_decidir": sum(not decision for decision in decisiones),
        "accepted": decisiones.count("ADD"),
        "discarded": decisiones.count("DISCARD"),
        "remaining_pending": pendientes,
        "decisiones_registradas": sum(bool(decision) for decision in decisiones),
        "por_tipo": {
            "competencia_tecnica": {
                "total": len(filas),
                "requieren_decision": sum(not decision for decision in decisiones),
                "accepted": decisiones.count("ADD"),
                "remaining_pending": pendientes,
            }
        },
        "revision": _revision(propuestas, journal),
        "materializacion": {
            "csv_canonicos_disponibles": all(
                (directorio / "salidas" / nombre).is_file()
                for nombre, _ in salida_catalogos.ARCHIVOS_CATALOGO
            )
        },
        "release_gate": gate,
    }


def pendientes_para_api(
    directorio_ejecucion: Path,
    *,
    desde: int = 0,
    limite: int = 50,
    incluir_resueltas: bool = True,
) -> dict[str, object]:
    directorio = _validar_directorio(directorio_ejecucion)
    manifest = _cargar_manifest(directorio)
    if not es_ejecucion_curricular(manifest):
        raise AprobacionNoPermitida("La ejecución no corresponde al pipeline curricular.")
    propuestas = _cargar_propuestas(directorio)
    journal = _cargar_journal(directorio)
    filas = _filas_actuales(propuestas, journal)
    if incluir_resueltas:
        visibles = filas
    else:
        visibles = [fila for fila in filas if fila.get("decision") in {None, "KEEP_PENDING"}]
    resumen = _resumen(directorio, propuestas, journal)
    return {
        "id_ejecucion": directorio.name,
        "total": len(visibles),
        "desde": desde,
        "limite": limite,
        "filas": visibles[desde : desde + limite],
        "revision": resumen["revision"],
        "aprobacion": resumen,
    }


def _validar_estado(manifest: Mapping[str, object]) -> None:
    estado = str(manifest.get("estado") or "")
    if estado not in _ESTADOS_TERMINALES:
        raise AprobacionNoPermitida(
            "La aprobación solo está disponible cuando la ejecución ha terminado "
            f"correctamente; estado actual: {estado or 'desconocido'}."
        )


def _leer_registros(directorio: Path) -> list[dict[str, object]]:
    ruta = directorio / "limpios" / "silabos.jsonl"
    registros = _leer_jsonl(ruta, requerido=True)
    for registro in registros:
        datos = registro.get("datos")
        if not isinstance(datos, Mapping):
            raise DecisionCurricularInvalida(
                "Los registros limpios tienen una estructura inválida."
            )
        if (
            not str(registro.get("id_curso") or "").strip()
            or not str(registro.get("id_silabo") or "").strip()
        ):
            raise DecisionCurricularInvalida(
                "Los registros limpios carecen de identidad curricular."
            )
    return registros


def _escribir_texto_atomico(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.technical.tmp")
    try:
        temporal.write_text(contenido, encoding="utf-8")
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)


def _escribir_json_atomico(ruta: Path, valor: Mapping[str, object]) -> None:
    _escribir_texto_atomico(ruta, json.dumps(valor, ensure_ascii=False, indent=2) + "\n")


def _escribir_journal_atomico(ruta: Path, filas: Sequence[Mapping[str, object]]) -> None:
    contenido = "".join(
        json.dumps(dict(fila), ensure_ascii=False, separators=(",", ":")) + "\n" for fila in filas
    )
    _escribir_texto_atomico(ruta, contenido)


def _capturar_arbol(directorio: Path) -> dict[Path, bytes]:
    return {
        ruta: ruta.read_bytes()
        for ruta in directorio.rglob("*")
        if ruta.is_file() and not ruta.is_symlink()
    }


def _restaurar_arbol(directorio: Path, snapshot: Mapping[Path, bytes]) -> None:
    for ruta in directorio.rglob("*"):
        if ruta.is_file() and not ruta.is_symlink() and ruta not in snapshot:
            ruta.unlink(missing_ok=True)
    for ruta, contenido in snapshot.items():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)


def _gate_tecnico(
    gate: Mapping[str, object],
    *,
    propuestas: Sequence[Mapping[str, object]],
    journal: Sequence[Mapping[str, object]],
    reconstruccion_ok: bool,
    error_estructural: str = "",
) -> dict[str, object]:
    filas = _filas_actuales(propuestas, journal)
    decisiones = [str(fila.get("decision") or "") for fila in filas]
    pendientes = sum(decision in {"", "KEEP_PENDING"} for decision in decisiones)
    checks_value = gate.get("checks")
    checks: dict[str, object] = dict(checks_value) if isinstance(checks_value, Mapping) else {}
    structural_previo = checks.get("structural_validation")
    if not isinstance(structural_previo, Mapping):
        structural_previo = checks.get("structural_errors")
    structural_previo_ok = not isinstance(structural_previo, Mapping) or bool(
        structural_previo.get("ok", True)
    )
    structural = {
        "ok": not error_estructural and structural_previo_ok,
        "error": error_estructural,
    }
    checks["structural_validation"] = structural
    checks["technical_approval"] = {
        "ok": pendientes == 0,
        "total_proposals": len(propuestas),
        "add": decisiones.count("ADD"),
        "discard": decisiones.count("DISCARD"),
        "keep_pending": decisiones.count("KEEP_PENDING"),
        "pending_decision": decisiones.count(""),
        "all_decided": pendientes == 0,
    }
    checks["technical_reconstruction"] = {"ok": reconstruccion_ok}
    blockers_value = gate.get("blockers")
    blockers: set[str] = (
        {str(item) for item in blockers_value if item}
        if isinstance(blockers_value, list)
        else set()
    )
    blockers.discard("PENDING_TECHNICAL_APPROVAL")
    if pendientes:
        blockers.add("PENDING_TECHNICAL_APPROVAL")
    if not reconstruccion_ok:
        blockers.add("TECHNICAL_RECONSTRUCTION_FAILED")
    if error_estructural or not structural["ok"]:
        blockers.add("STRUCTURAL_VALIDATION_FAILED")
    resultado = dict(gate)
    resultado["decision"] = "ALLOW_IMPORT" if not blockers else "BLOCK_IMPORT"
    resultado["blockers"] = sorted(blockers)
    resultado["checks"] = checks
    observability_value = gate.get("observability")
    observability = dict(observability_value) if isinstance(observability_value, Mapping) else {}
    resultado["observability"] = {**observability, "pending_records": pendientes}
    return resultado


def _persistir_manifest(
    directorio: Path,
    manifest: Mapping[str, object],
    gate: Mapping[str, object],
    resumen: Mapping[str, object],
) -> None:
    actualizado = dict(manifest)
    actualizado["release_gate"] = dict(gate)
    actualizado["aprobacion_curricular"] = dict(resumen)
    actualizado["actualizada_en"] = datetime.now(UTC).isoformat()
    _escribir_json_atomico(directorio / "manifest.json", actualizado)


def _materializar(
    directorio: Path,
    manifest: Mapping[str, object],
    propuestas: Sequence[Mapping[str, object]],
    journal: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, Mapping) else {}
    carrera = str(parametros.get("carrera") or "").strip()
    periodo = str(parametros.get("periodo") or "").strip()
    if not carrera or not periodo:
        raise DecisionCurricularInvalida("La ejecución técnica no tiene carrera y periodo.")
    decisiones = _decisiones_por_id(journal)
    aprobadas = [
        {**dict(propuesta), "estado_aprobacion": "APROBADA"}
        for propuesta in propuestas
        if str(decisiones.get(str(propuesta["id_propuesta"]), {}).get("decision") or "") == "ADD"
    ]
    pendientes = [
        dict(propuesta)
        for propuesta in propuestas
        if str(decisiones.get(str(propuesta["id_propuesta"]), {}).get("decision") or "")
        in {"", "KEEP_PENDING"}
    ]
    analisis = _leer_json(_reportes(directorio) / "analisis_tecnico.json")
    resultado = construir_salidas_tecnicas(
        _leer_registros(directorio),
        directorio / "salidas",
        carrera=carrera,
        periodo_academico=periodo,
        propuestas_tecnicas=pendientes,
        propuestas_aprobadas=aprobadas,
        analisis_tecnico=analisis or {"estado": "COMPLETADO"},
    )
    gate = _gate_tecnico(
        resultado.release_gate,
        propuestas=propuestas,
        journal=journal,
        reconstruccion_ok=True,
    )
    _escribir_json_atomico(_reportes(directorio) / "release_gate.json", gate)
    return gate


def _validar_solicitudes(
    decisiones: Sequence[Mapping[str, object]],
    propuestas: Sequence[Mapping[str, object]],
    journal: Sequence[Mapping[str, object]],
    revision: str | None,
) -> tuple[list[dict[str, object]], str]:
    revision_actual = _revision(propuestas, journal)
    ids = {str(propuesta.get("id_propuesta") or "") for propuesta in propuestas}
    anteriores = _decisiones_por_id(journal)
    repeticion_idempotente = all(
        str(solicitud.get("id_pendiente") or "") in anteriores
        and str(anteriores[str(solicitud.get("id_pendiente") or "")].get("decision") or "")
        == str(solicitud.get("decision") or "").upper()
        for solicitud in decisiones
    )
    if revision != revision_actual and not repeticion_idempotente:
        raise RevisionCurricularInvalida(
            "La cola técnica cambió; recarga la revisión curricular antes de decidir."
        )
    validadas: list[dict[str, object]] = []
    vistos: set[str] = set()
    for solicitud in decisiones:
        identificador = str(solicitud.get("id_pendiente") or "").strip()
        decision = str(solicitud.get("decision") or "").strip().upper()
        reason = str(solicitud.get("reason") or "").strip()[:600]
        if not identificador or identificador not in ids:
            raise DecisionCurricularInvalida(
                f"No existe la propuesta técnica {identificador!r} en esta ejecución."
            )
        if decision not in _DECISIONES_VALIDAS:
            raise DecisionCurricularInvalida(f"Decisión técnica inválida: {decision!r}.")
        if decision == "DISCARD" and not reason:
            raise DecisionCurricularInvalida("Descartar una propuesta técnica requiere un motivo.")
        if identificador in vistos:
            raise DecisionCurricularInvalida(f"La propuesta {identificador!r} aparece duplicada.")
        vistos.add(identificador)
        previa = anteriores.get(identificador)
        decision_previa = str(previa.get("decision") or "") if previa else ""
        if decision_previa and decision_previa != decision:
            raise DecisionCurricularInvalida(
                f"La propuesta técnica {identificador!r} ya tiene otra decisión."
            )
        validadas.append(
            {
                **dict(solicitud),
                "id_propuesta": identificador,
                "decision": decision,
                "reason": reason,
            }
        )
    return validadas, revision_actual


def aplicar_decisiones(
    directorio_ejecucion: Path,
    decisiones: Sequence[Mapping[str, object]],
    *,
    actor: str = "ejecutor",
    revision: str | None = None,
) -> dict[str, object]:
    directorio = _validar_directorio(directorio_ejecucion)
    with _LOCK:
        manifest = _cargar_manifest(directorio)
        if not es_ejecucion_curricular(manifest):
            raise AprobacionNoPermitida("La ejecución no corresponde al pipeline curricular.")
        _validar_estado(manifest)
        propuestas = _cargar_propuestas(directorio)
        journal = _cargar_journal(directorio)
        validadas, revision_actual = _validar_solicitudes(decisiones, propuestas, journal, revision)
        if not validadas:
            resumen = _resumen(directorio, propuestas, journal)
            return {
                "aprobacion": resumen,
                "filas": _filas_actuales(propuestas, journal),
                "revision": revision_actual,
            }

        ahora = datetime.now(UTC).isoformat()
        previas = _decisiones_por_id(journal)
        nuevas: list[dict[str, object]] = []
        for solicitud in validadas:
            identificador = str(solicitud["id_propuesta"])
            if identificador in previas:
                continue
            propuesta = next(
                propuesta
                for propuesta in propuestas
                if str(propuesta["id_propuesta"]) == identificador
            )
            nuevas.append(
                {
                    "id_propuesta": identificador,
                    "decision": solicitud["decision"],
                    "actor": str(actor or "ejecutor")[:200],
                    "decidido_en": ahora,
                    "revision": revision_actual,
                    "reason": str(solicitud.get("reason") or "")[:600],
                    "propuesta": dict(propuesta),
                    "evidencia": _evidencia_literal(propuesta),
                }
            )
        journal_candidato = [*journal, *nuevas]
        snapshot = _capturar_arbol(directorio)
        try:
            gate = _materializar(directorio, manifest, propuestas, journal_candidato)
            if nuevas:
                _escribir_journal_atomico(
                    _reportes(directorio) / DECISIONES_ARCHIVO,
                    journal_candidato,
                )
            resumen = _resumen(directorio, propuestas, journal_candidato)
            resumen["release_gate"] = gate
            _persistir_manifest(directorio, manifest, gate, resumen)
        except Exception:
            _restaurar_arbol(directorio, snapshot)
            raise

        return {
            "aprobacion": resumen,
            "filas": _filas_actuales(propuestas, journal_candidato),
            "revision": _revision(propuestas, journal_candidato),
        }


def resumen_aprobacion_curricular(directorio_ejecucion: Path) -> dict[str, object]:
    directorio = _validar_directorio(directorio_ejecucion)
    propuestas = _cargar_propuestas(directorio)
    journal = _cargar_journal(directorio)
    return _resumen(directorio, propuestas, journal)


def filas_para_presentacion_api(
    filas: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    return list(filas)
