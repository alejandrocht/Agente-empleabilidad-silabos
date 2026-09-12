"""Derived post-HITL approval artifacts without approval transaction ownership."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.silabos.clasificacion import (
    estado_clasificacion,
    puede_recibir_decision,
    requiere_resolucion_curricular,
)
from agente.normalizador.silabos.integridad_chh import validar_integridad_chh
from agente.normalizador.silabos.paquetes import (
    ensamblar_paquetes_chh,
    validar_integridad_paquetes_chh,
)
from agente.normalizador.silabos.perfiles import _CATALOGO_PERFIL
from agente.normalizador.silabos.persistencia_aprobaciones import (
    ExceptionFactory,
    _clave_ruta,
    _escribir_csv_atomico,
    _escribir_json_atomico,
    _escribir_texto_atomico,
    _leer_json_dict,
    _leer_jsonl,
    _texto,
)
from agente.normalizador.silabos.salida import (
    ARCHIVOS_SALIDA,
    COBERTURA_SCHEMA,
    COMPETENCIAS_SCHEMA,
    HERRAMIENTAS_SCHEMA,
)

CANDIDATOS_ARCHIVO = "candidatos_curriculares.json"
DECISIONES_ARCHIVO = "decisiones_curriculares.jsonl"


def _recalcular_release_gate(
    reportes: Path,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    pendientes: list[dict[str, object]],
    *,
    materialized: bool = True,
    invalid_error: ExceptionFactory,
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
            archivos["catalogo_logros.csv"],
            "id_logro",
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
    relaciones_reportadas = _leer_jsonl(
        reportes / "cobertura_curricular_canonica.jsonl", invalid_error=invalid_error
    )
    relaciones_canonicas = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_logro")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in relaciones_reportadas
    }
    relaciones_csv = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_logro")),
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
        "id_logro": {_texto(fila.get("id_logro")) for fila in archivos["catalogo_logros.csv"]},
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
            _texto(fila.get("id_logro")),
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
            "canonical_skills": len(archivos["catalogo_logros.csv"]),
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
    *,
    catalog_root: Callable[[], Path],
    approval_summary: Callable[[Path], dict[str, object]],
    invalid_error: ExceptionFactory,
) -> None:
    if not _puede_materializar_perfil(gate):
        return
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera = _clave_ruta(_texto(parametros.get("carrera")))
    periodo = re.sub(r"[^0-9-]", "", _texto(parametros.get("periodo")))
    if not carrera or not periodo:
        raise invalid_error("La ejecución no tiene carrera y periodo materializables.")
    destino = catalog_root() / "carreras" / carrera / periodo
    destino.mkdir(parents=True, exist_ok=True)
    for nombre, columnas in ARCHIVOS_SALIDA:
        nombre_destino, columnas_destino, nuevos = _destino_catalogo(
            nombre, list(archivos[nombre]), columnas
        )
        actual = _leer_csv_opcional(
            destino / nombre_destino, columnas_destino, invalid_error=invalid_error
        )
        fusionadas = _fusionar_csv(actual, nuevos, columnas_destino)
        _escribir_csv_atomico(destino / nombre_destino, columnas_destino, fusionadas)
    reportes_destino = destino / "reportes"
    reportes_destino.mkdir(parents=True, exist_ok=True)
    for reporte in reportes.iterdir():
        if reporte.is_file() and reporte.suffix in {".json", ".jsonl"}:
            _escribir_texto_atomico(
                reportes_destino / reporte.name, reporte.read_text(encoding="utf-8")
            )
    nombre_habilidades, columnas_habilidades, _ = _destino_catalogo("catalogo_logros.csv", [], ())
    conteos = {
        "competencias": len(
            _leer_csv_opcional(
                destino / "catalogo_competencias.csv",
                COMPETENCIAS_SCHEMA,
                invalid_error=invalid_error,
            )
        ),
        "habilidades": len(
            _leer_csv_opcional(
                destino / nombre_habilidades,
                columnas_habilidades,
                invalid_error=invalid_error,
            )
        ),
        "herramientas": len(
            _leer_csv_opcional(
                destino / "catalogo_herramientas.csv",
                HERRAMIENTAS_SCHEMA,
                invalid_error=invalid_error,
            )
        ),
        "cobertura": len(
            _leer_csv_opcional(
                destino / "cobertura_curricular.csv",
                COBERTURA_SCHEMA,
                invalid_error=invalid_error,
            )
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
            "aprobacion_curricular": approval_summary(directorio),
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
    """Persist derived state so a restart retains the approval decision."""

    manifest["release_gate"] = gate
    manifest["aprobacion_curricular"] = resumen
    from datetime import UTC, datetime

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
        limpieza["habilidades"] = len(archivos["catalogo_logros.csv"])
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


def _destino_catalogo(
    nombre: str,
    filas: list[dict[str, str]],
    columnas: tuple[str, ...],
) -> tuple[str, tuple[str, ...], list[dict[str, str]]]:
    """Nombra el catálogo de destino y traduce sus columnas al contrato interno.

    El perfil de carrera alimenta el lector de catálogos curados, que todavía
    espera el contrato de habilidades; el catálogo publicado son los logros.
    """

    nombre_destino, reescritura = _CATALOGO_PERFIL.get(nombre, (nombre, ()))
    if not reescritura:
        return nombre, columnas, filas
    return (
        nombre_destino,
        tuple(destino_columna for destino_columna, _ in reescritura),
        [
            {
                destino_columna: fila.get(columna_origen, "")
                for destino_columna, columna_origen in reescritura
            }
            for fila in filas
        ],
    )


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


def _leer_csv_opcional(
    ruta: Path, columnas: tuple[str, ...], *, invalid_error: ExceptionFactory
) -> list[dict[str, str]]:
    if not ruta.is_file():
        return []
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if tuple(lector.fieldnames or ()) != columnas:
            raise invalid_error(f"El esquema de {ruta.name} no coincide con el perfil.")
        return [{columna: _texto(fila.get(columna)) for columna in columnas} for fila in lector]
