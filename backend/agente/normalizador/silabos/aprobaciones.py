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
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from agente.normalizador.empleabilidad.catalogo import clave_concepto, ruta_catalogos
from agente.normalizador.silabos.clasificacion import (
    clasificar_propuestas,
    puede_recibir_decision,
    resumen_clasificacion,
)
from agente.normalizador.silabos.salida import (
    ARCHIVOS_SALIDA,
    COBERTURA_SCHEMA,
    COMPETENCIAS_SCHEMA,
    HABILIDADES_SCHEMA,
    HERRAMIENTAS_SCHEMA,
)

PENDIENTES_ARCHIVO = "pendientes_curriculares.jsonl"
DECISIONES_ARCHIVO = "decisiones_curriculares.jsonl"
CANDIDATOS_ARCHIVO = "candidatos_curriculares.json"
ESTADOS_PENDIENTES = {
    "PENDIENTE_CATALOGACION",
    "PENDIENTE_AMPLIACION_PERFIL",
    "REQUIERE_REVISION_HUMANA",
    "MANTENIDA_PENDIENTE",
}
DECISIONES_VALIDAS = {"ADD", "KEEP_PENDING"}
ESTADOS_APROBACION = {"limpiado", "limpiado_con_advertencias"}
_ID_EJECUCION = re.compile(r"NOR_[0-9a-f]{16}")
_LOCK = RLock()


class DecisionCurricularInvalida(ValueError):
    """La solicitud no cumple el contrato de decisiones curriculares."""


class AprobacionNoPermitida(RuntimeError):
    """La ejecución no está en un estado seguro para recibir decisiones."""


def resumen_aprobacion_curricular(directorio_ejecucion: Path) -> dict[str, object]:
    """Resume la cola sin ocultar decisiones ya registradas."""

    ruta_pendientes = directorio_ejecucion / "salidas" / "reportes" / PENDIENTES_ARCHIVO
    filas = clasificar_propuestas(_leer_jsonl(ruta_pendientes))
    sin_decidir = [
        fila
        for fila in filas
        if puede_recibir_decision(fila) and not _texto(fila.get("decision"))
    ]
    aceptadas = [
        fila
        for fila in filas
        if not fila.get("auto_deduplicated") and fila.get("decision") == "ADD"
    ]
    mantenidas = [
        fila
        for fila in filas
        if not fila.get("auto_deduplicated") and fila.get("decision") == "KEEP_PENDING"
    ]
    por_tipo: dict[str, dict[str, int]] = {}
    for fila in filas:
        tipo = _texto(fila.get("tipo")) or "otro"
        acumulado = por_tipo.setdefault(
            tipo,
            {"total": 0, "requieren_decision": 0, "accepted": 0, "remaining_pending": 0},
        )
        acumulado["total"] += 1
        if puede_recibir_decision(fila) and not _texto(fila.get("decision")):
            acumulado["requieren_decision"] += 1
        elif not fila.get("auto_deduplicated") and fila.get("decision") == "ADD":
            acumulado["accepted"] += 1
        elif not fila.get("auto_deduplicated") and fila.get("decision") == "KEEP_PENDING":
            acumulado["remaining_pending"] += 1
    clasificacion = resumen_clasificacion(filas)
    return {
        "requiere_decision": bool(sin_decidir),
        "total": len(filas),
        "pendientes_por_decidir": len(sin_decidir),
        "accepted": len(aceptadas),
        "remaining_pending": len(sin_decidir) + len(mantenidas),
        "decisiones_registradas": len(aceptadas) + len(mantenidas),
        "auto_deduplicated": sum(bool(fila.get("auto_deduplicated")) for fila in filas),
        "por_tipo": por_tipo,
        "clasificacion": clasificacion,
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


def pendientes_para_revision(directorio_ejecucion: Path) -> list[dict[str, object]]:
    """Devuelve solo propuestas todavía no decididas por el ejecutor."""

    ruta = directorio_ejecucion / "salidas" / "reportes" / PENDIENTES_ARCHIVO
    return [
        fila
        for fila in clasificar_propuestas(_leer_jsonl(ruta))
        if puede_recibir_decision(fila) and not _texto(fila.get("decision"))
    ]


def aplicar_decisiones_curriculares(
    directorio_ejecucion: Path,
    decisiones: list[dict[str, object]],
    *,
    actor: str = "ejecutor",
) -> dict[str, object]:
    """Aplica decisiones idempotentes y materializa el perfil curricular.

    ``ADD`` promueve únicamente al perfil de carrera/periodo. ``KEEP_PENDING``
    deja la propuesta y su evidencia fuera de los CSV canónicos. Ambas ramas
    quedan registradas en un JSONL de decisiones para que una repetición de la
    misma petición no duplique filas ni decisiones.
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
        pendientes = clasificar_propuestas(_leer_jsonl(reportes / PENDIENTES_ARCHIVO))
        por_id = {str(fila.get("id_pendiente")): fila for fila in pendientes}
        decisiones_previas = _leer_decisiones(reportes / DECISIONES_ARCHIVO)

        for solicitud in solicitudes:
            id_pendiente = solicitud["id_pendiente"]
            decision = solicitud["decision"]
            if id_pendiente not in por_id:
                raise DecisionCurricularInvalida(
                    f"No existe el pendiente {id_pendiente!r} en esta ejecución."
                )
            if por_id[id_pendiente].get("auto_deduplicated"):
                representante = _texto(
                    por_id[id_pendiente].get("exact_duplicate_representative_id")
                )
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
        nuevas_decisiones: list[dict[str, object]] = []
        candidatos = _cargar_candidatos(reportes)
        archivos = candidatos or _cargar_archivos_curriculares(directorio / "salidas")
        fuentes = _cargar_fuentes(reportes)
        relaciones = list(archivos["cobertura_curricular.csv"])

        for solicitud in solicitudes:
            id_pendiente = solicitud["id_pendiente"]
            decision = solicitud["decision"]
            fila = por_id[id_pendiente]
            # Una repetición exacta es un no-op. Sigue participando en el
            # resumen para que el cliente reciba exactamente el mismo estado.
            if id_pendiente in decisiones_previas or _texto(fila.get("decision")):
                if decision == "ADD":
                    filas_aceptadas += 1
                else:
                    filas_mantenidas += 1
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
                "decision": decision,
                "actor": actor_normalizado,
                "decidido_en": ahora,
                "id_canonico": id_canonico or None,
                "tipo": _texto(fila.get("tipo")),
                "evidencia": _evidencia(fila),
            }
            nuevas_decisiones.append(nueva)

        todas_decididas = not any(
            puede_recibir_decision(fila) and not _texto(fila.get("decision"))
            for fila in pendientes
        )
        if todas_decididas:
            _escribir_archivos_curriculares(directorio / "salidas", archivos)
        else:
            # A partial batch is still useful state, but it must not expose a
            # canonical package before every proposal has an explicit outcome.
            _eliminar_archivos_curriculares(directorio / "salidas")
        _escribir_fuentes(reportes, fuentes)
        _escribir_relaciones(directorio / "salidas", reportes, relaciones)
        _escribir_jsonl_atomico(reportes / PENDIENTES_ARCHIVO, pendientes)
        _escribir_candidatos(reportes, archivos, materialized=todas_decididas)
        gate = _recalcular_release_gate(
            reportes,
            archivos,
            fuentes,
            pendientes,
            materialized=todas_decididas,
        )
        _escribir_json_atomico(reportes / "release_gate.json", gate)
        _append_decisiones(reportes / DECISIONES_ARCHIVO, nuevas_decisiones)
        if todas_decididas:
            _materializar_perfil(directorio, manifest, archivos, reportes, pendientes, gate)

        resumen = resumen_aprobacion_curricular(directorio)
        resumen["accepted_in_request"] = filas_aceptadas
        resumen["kept_pending_in_request"] = filas_mantenidas
        resumen["release_gate"] = gate
        _persistir_manifest_aprobacion(directorio, manifest, archivos, gate, resumen)
        return {"aprobacion": resumen}


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


def _validar_solicitudes(decisiones: list[dict[str, object]]) -> list[dict[str, str]]:
    if not isinstance(decisiones, list) or not decisiones:
        raise DecisionCurricularInvalida("Debe enviar al menos una decisión curricular.")
    resultado: list[dict[str, str]] = []
    ids: set[str] = set()
    for item in decisiones:
        if not isinstance(item, dict):
            raise DecisionCurricularInvalida("Cada decisión debe ser un objeto.")
        id_pendiente = _texto(item.get("id_pendiente"))
        decision = _texto(item.get("decision")).upper()
        if not id_pendiente or len(id_pendiente) > 200:
            raise DecisionCurricularInvalida("Cada decisión necesita un id_pendiente válido.")
        if decision not in DECISIONES_VALIDAS:
            raise DecisionCurricularInvalida(
                f"Decisión inválida para {id_pendiente!r}; use ADD o KEEP_PENDING."
            )
        if id_pendiente in ids:
            raise DecisionCurricularInvalida("La solicitud contiene ids duplicados.")
        ids.add(id_pendiente)
        resultado.append({"id_pendiente": id_pendiente, "decision": decision})
    return resultado


def _promover(
    fila: dict[str, object],
    propuesta: dict[str, object],
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, str]],
) -> str:
    tipo = _texto(fila.get("tipo")).lower()
    nombre = _texto(propuesta.get("nombre") or propuesta.get("id"))
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
                "id_competencia_fuente": _id_canonico(
                    "COMP_SRC", carrera, periodo, str(fila.get("id_pendiente"))
                ),
                "id_curso": _texto(fila.get("id_curso")),
                "id_silabo": _texto(fila.get("id_silabo")),
                "archivo": _texto(fila.get("archivo")),
                "codigo_competencia": "LLM",
                "nombre_competencia_fuente": nombre,
                "descripcion_fuente": _texto(fila.get("descripcion_fuente")) or descripcion,
                "id_competencia_canonica": id_canonico,
                "id_habilidad_fuente": _texto(fila.get("id_habilidad_fuente")),
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
        id_fuente = _texto(fila.get("id_habilidad_fuente")) or _id_canonico(
            "HAB_SRC", carrera, periodo, str(fila.get("id_pendiente"))
        )
        _upsert_fuente(
            fuentes["habilidades_fuente.jsonl"],
            "id_habilidad_fuente",
            {
                "id_habilidad_fuente": id_fuente,
                "id_curso": _texto(fila.get("id_curso")),
                "id_silabo": _texto(fila.get("id_silabo")),
                "archivo": _texto(fila.get("archivo")),
                "etiqueta_logro": _texto(fila.get("etiqueta_logro")),
                "descripcion_fuente": _texto(fila.get("descripcion_fuente")) or descripcion,
                "id_habilidad_canonica": id_canonico,
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
                "metodo_resolucion": "APROBACION_EJECUTOR",
                "evidencia_fuente": _evidencia(fila),
            },
        )
    elif tipo == "herramienta":
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
                "id_herramienta_fuente": _id_canonico(
                    "HERR_SRC", carrera, periodo, str(fila.get("id_pendiente"))
                ),
                "id_curso": _texto(fila.get("id_curso")),
                "id_silabo": _texto(fila.get("id_silabo")),
                "id_habilidad_fuente": _texto(fila.get("id_habilidad_fuente")),
                "id_herramienta_canonica": id_canonico,
                "nombre_herramienta": nombre,
                "seccion_fuente": "APROBACION_EJECUTOR",
                "texto_evidencia": "; ".join(str(x) for x in _evidencia(fila)),
                "coincidencia": "APROBACION_EJECUTOR",
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
    relaciones: list[dict[str, str]],
) -> None:
    """Añade relaciones solo cuando los tres extremos son verificables."""

    id_curso = _texto(fila.get("id_curso"))
    id_silabo = _texto(fila.get("id_silabo"))
    id_habilidad_fuente = _texto(fila.get("id_habilidad_fuente"))
    if not id_curso or not id_silabo:
        return
    habilidades = {
        _texto(item.get("id_habilidad_fuente")): _texto(item.get("id_habilidad_canonica"))
        for item in fuentes["habilidades_fuente.jsonl"]
    }
    skill_id = id_canonico if tipo == "habilidad" else habilidades.get(id_habilidad_fuente, "")
    if not skill_id:
        return
    comp_ids = [
        _texto(item.get("id_competencia_canonica"))
        for item in fuentes["competencias_fuente.jsonl"]
        if _texto(item.get("id_silabo")) == id_silabo
        and _texto(item.get("id_competencia_canonica"))
    ]
    if tipo == "competencia":
        comp_ids = [id_canonico]
    tool_ids = [
        _texto(item.get("id_herramienta_canonica"))
        for item in fuentes["herramientas_fuente.jsonl"]
        if _texto(item.get("id_silabo")) == id_silabo
        and _texto(item.get("id_herramienta_canonica"))
    ]
    if tipo == "herramienta":
        tool_ids = [id_canonico]
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
        herramientas_finales = [tool for tool in dict.fromkeys(tool_ids) if tool in valid_tool] or [
            ""
        ]
        for tool_id in herramientas_finales:
            _upsert_relacion(relaciones, id_curso, id_silabo, comp_id, skill_id, tool_id)


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
    relaciones: list[dict[str, str]],
    id_curso: str,
    id_silabo: str,
    id_competencia: str,
    id_habilidad: str,
    id_herramienta: str,
) -> None:
    clave = (id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta)
    existentes = {
        (
            _texto(row.get("id_curso")),
            _texto(row.get("id_silabo")),
            _texto(row.get("id_competencia")),
            _texto(row.get("id_habilidad")),
            _texto(row.get("id_herramienta")),
        )
        for row in relaciones
    }
    if clave not in existentes:
        relaciones.append(_fila_relacion(*clave))


def _fila_relacion(
    id_curso: str,
    id_silabo: str,
    id_competencia: str,
    id_habilidad: str,
    id_herramienta: str,
) -> dict[str, str]:
    return {
        "id_cob_curricular": _id_canonico(
            "COB_CUR", id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta
        ),
        "id_curso": id_curso,
        "id_silabo": id_silabo,
        "id_competencia": id_competencia,
        "id_habilidad": id_habilidad,
        "id_herramienta": id_herramienta,
    }


def _cargar_archivos_curriculares(salida: Path) -> dict[str, list[dict[str, str]]]:
    archivos: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in ARCHIVOS_SALIDA:
        ruta = salida / nombre
        filas: list[dict[str, str]] = []
        if ruta.is_file():
            with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
                lector = csv.DictReader(archivo)
                if tuple(lector.fieldnames or ()) != columnas:
                    raise DecisionCurricularInvalida(
                        f"El esquema de {nombre} no coincide con la salida curricular."
                    )
                filas = [
                    {columna: str(fila.get(columna) or "") for columna in columnas}
                    for fila in lector
                ]
        archivos[nombre] = filas
    return archivos


def _cargar_candidatos(reportes: Path) -> dict[str, list[dict[str, str]]] | None:
    """Carga el paquete candidato sin confundirlo con los CSV publicables."""

    ruta = reportes / CANDIDATOS_ARCHIVO
    if not ruta.is_file():
        return None
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionCurricularInvalida(
            f"Reporte de candidatos curriculares inválido: {ruta.name}."
        ) from exc
    if not isinstance(contenido, dict) or not isinstance(contenido.get("archivos"), dict):
        raise DecisionCurricularInvalida("El reporte de candidatos curriculares no es válido.")
    resultado: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in ARCHIVOS_SALIDA:
        filas = contenido["archivos"].get(nombre, [])
        if not isinstance(filas, list):
            raise DecisionCurricularInvalida(
                f"Los candidatos de {nombre} no tienen una lista válida."
            )
        resultado[nombre] = [
            {columna: str(fila.get(columna) or "") for columna in columnas}
            for fila in filas
            if isinstance(fila, dict)
        ]
    return resultado


def _cargar_fuentes(reportes: Path) -> dict[str, list[dict[str, object]]]:
    return {
        nombre: _leer_jsonl(reportes / nombre)
        for nombre in (
            "competencias_fuente.jsonl",
            "habilidades_fuente.jsonl",
            "herramientas_fuente.jsonl",
        )
    }


def _cargar_relaciones(salida: Path, reportes: Path) -> list[dict[str, str]]:
    ruta = salida / "cobertura_curricular.csv"
    if ruta.is_file():
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            return [
                {columna: str(fila.get(columna) or "") for columna in COBERTURA_SCHEMA}
                for fila in lector
            ]
    return []


def _escribir_archivos_curriculares(
    salida: Path, archivos: dict[str, list[dict[str, str]]]
) -> None:
    for nombre, columnas in ARCHIVOS_SALIDA:
        filas = archivos[nombre]
        filas.sort(
            key=lambda fila: tuple(clave_concepto(fila.get(columna, "")) for columna in columnas)
        )
        _escribir_csv_atomico(salida / nombre, columnas, filas)


def _eliminar_archivos_curriculares(salida: Path) -> None:
    """Removes stale canonical files while a proposal batch is unresolved."""

    for nombre, _ in ARCHIVOS_SALIDA:
        ruta = salida / nombre
        try:
            ruta.unlink(missing_ok=True)
        except OSError as exc:
            raise AprobacionNoPermitida(
                f"No se pudo retirar el CSV canónico pendiente: {nombre}."
            ) from exc


def _escribir_candidatos(
    reportes: Path,
    archivos: dict[str, list[dict[str, str]]],
    *,
    materialized: bool,
) -> None:
    """Persists the full candidate package before or alongside CSV materialization."""

    contenido = {
        "version": "curricular-candidates/v1",
        "materialized": materialized,
        "archivos": {nombre: list(archivos[nombre]) for nombre, _ in ARCHIVOS_SALIDA},
        "decision_policy": {
            "exact_duplicates": "AUTO_DEDUPLICATE",
            "semantic_duplicates": "REVIEW_ONLY",
            "suspicious_tools": "REVIEW_ONLY",
            "auto_delete": False,
            "auto_merge": False,
            "source_rows_preserved": True,
        },
    }
    _escribir_json_atomico(reportes / CANDIDATOS_ARCHIVO, contenido)


def _escribir_fuentes(reportes: Path, fuentes: dict[str, list[dict[str, object]]]) -> None:
    for nombre, filas in fuentes.items():
        _escribir_jsonl_atomico(reportes / nombre, filas)


def _escribir_relaciones(salida: Path, reportes: Path, relaciones: list[dict[str, str]]) -> None:
    relaciones.sort(
        key=lambda fila: tuple(_texto(fila.get(columna)) for columna in COBERTURA_SCHEMA)
    )
    _escribir_jsonl_atomico(
        reportes / "cobertura_curricular_canonica.jsonl",
        relaciones,
    )


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
            _texto(fila.get("id_competencia"))
            for fila in archivos["catalogo_competencias.csv"]
        },
        "id_habilidad": {
            _texto(fila.get("id_habilidad"))
            for fila in archivos["catalogo_habilidades.csv"]
        },
        "id_herramienta": {
            _texto(fila.get("id_herramienta"))
            for fila in archivos["catalogo_herramientas.csv"]
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
        if not fila.get("auto_deduplicated") and fila.get("decision") == "ADD"
    )
    kept_pending = sum(
        1
        for fila in pendientes
        if not fila.get("auto_deduplicated") and fila.get("decision") == "KEEP_PENDING"
    )
    undecided = sum(
        1
        for fila in pendientes
        if puede_recibir_decision(fila) and not _texto(fila.get("decision"))
    )
    gate["approval"] = {
        "accepted": accepted,
        "remaining_pending": kept_pending + undecided,
        "pending_decision": undecided,
        "decisions_recorded": accepted + kept_pending,
        "auto_deduplicated": sum(bool(fila.get("auto_deduplicated")) for fila in pendientes),
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
        "STRUCTURAL_ERRORS_PRESENT",
    }
    blockers = {
        str(item)
        for item in gate.get("blockers", [])
        if item and str(item) not in dynamic_blockers
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
    checks["approval"] = {
        "ok": undecided == 0 and materialized,
        "pending_decision": undecided,
        "canonical_materialized": materialized,
    }
    if undecided:
        blockers.add("PENDING_DECISIONS")
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


def _materializar_perfil(
    directorio: Path,
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    reportes: Path,
    pendientes: list[dict[str, object]],
    gate: dict[str, object],
) -> None:
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
            if not fila.get("auto_deduplicated") and fila.get("decision") != "ADD"
        ),
    }
    perfil = _leer_json_dict(destino / "perfil.json")
    perfil.update(
        {
            "tipo": "bootstrap_silabos",
            "estado": "BORRADOR_CON_PENDIENTES" if conteos["pendientes"] else "BORRADOR",
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
        archivos_candidatos = (
            archivos_candidatos if isinstance(archivos_candidatos, dict) else {}
        )
        item["registros"] = sum(
            len(filas)
            for filas in archivos_candidatos.values()
            if isinstance(filas, list)
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


def _leer_jsonl(ruta: Path) -> list[dict[str, object]]:
    if not ruta.is_file():
        return []
    filas: list[dict[str, object]] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            valor = json.loads(linea)
        except json.JSONDecodeError as exc:
            raise DecisionCurricularInvalida(f"Reporte JSONL inválido: {ruta.name}.") from exc
        if isinstance(valor, dict):
            filas.append(valor)
    return filas


def _leer_json_dict(ruta: Path) -> dict[str, object]:
    if not ruta.is_file():
        return {}
    try:
        valor = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return valor if isinstance(valor, dict) else {}


def _escribir_csv_atomico(
    ruta: Path, columnas: tuple[str, ...], filas: list[dict[str, str]]
) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.approval.tmp")
    with temporal.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="raise")
        escritor.writeheader()
        escritor.writerows(
            {columna: fila.get(columna, "") for columna in columnas} for fila in filas
        )
    temporal.replace(ruta)


def _escribir_jsonl_atomico(
    ruta: Path, filas: Iterable[Mapping[str, object]]
) -> None:
    contenido = "".join(
        json.dumps(fila, ensure_ascii=False, separators=(",", ":")) + "\n" for fila in filas
    )
    _escribir_texto_atomico(ruta, contenido)


def _escribir_json_atomico(ruta: Path, valor: dict[str, object]) -> None:
    _escribir_texto_atomico(ruta, json.dumps(valor, ensure_ascii=False, indent=2) + "\n")


def _escribir_texto_atomico(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.approval.tmp")
    temporal.write_text(contenido, encoding="utf-8")
    temporal.replace(ruta)


def _id_canonico(tipo: str, *partes: str) -> str:
    prefijos = {
        "competencia": "COMP_PERFIL",
        "habilidad": "HAB_PERFIL",
        "herramienta": "HERR_PERFIL",
        "COMP_SRC": "COMP_SRC",
        "HAB_SRC": "HAB_SRC",
        "HERR_SRC": "HERR_SRC",
        "COB_CUR": "COB_CUR_CAN",
    }
    prefijo = prefijos.get(tipo, tipo)
    payload = "|".join(clave_concepto(parte) for parte in partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _clave_ruta(valor: str) -> str:
    normalizado = re.sub(r"[^A-Za-z0-9]+", "_", valor).strip("_").upper()
    return normalizado


def _texto(valor: Any) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _evidencia(fila: dict[str, object]) -> list[object]:
    evidencia = fila.get("evidencia")
    return list(evidencia) if isinstance(evidencia, list) else []
