"""Persistence primitives for post-approval curricular artifacts."""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.identidad import hashed
from agente.normalizador.silabos.salida import ARCHIVOS_SALIDA, COBERTURA_SCHEMA

CANDIDATOS_ARCHIVO = "candidatos_curriculares.json"
ExceptionFactory = Callable[[str], Exception]


def _rutas_transaccionales(
    directorio: Path,
    *,
    catalog_root: Path,
    not_permitted_error: ExceptionFactory,
) -> tuple[Path, ...]:
    try:
        manifest = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise not_permitted_error("No se pudo leer el manifest de la ejecución.") from exc
    if not isinstance(manifest, dict):
        raise not_permitted_error("El manifest de la ejecución no es válido.")
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera = _clave_ruta(_texto(parametros.get("carrera")))
    periodo = _texto(parametros.get("periodo"))
    carrera_root = catalog_root / "carreras" / carrera if carrera else None
    perfil = carrera_root / periodo if carrera_root is not None and periodo else None
    return (
        (directorio, carrera_root, perfil)
        if carrera_root is not None and perfil is not None
        else (directorio,)
    )


def _capturar_arboles(
    roots: tuple[Path, ...], *, not_permitted_error: ExceptionFactory
) -> dict[Path, bytes]:
    snapshot: dict[Path, bytes] = {}
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                try:
                    snapshot[path] = path.read_bytes()
                except OSError as exc:
                    raise not_permitted_error(
                        "No se pudo preparar la transacción de aprobación."
                    ) from exc
    return snapshot


def _restaurar_arboles(roots: tuple[Path, ...], snapshot: dict[Path, bytes]) -> None:
    for root in roots:
        if not root.exists() or root.is_symlink():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path not in snapshot:
                try:
                    path.unlink()
                except OSError:
                    pass
    for path, content in snapshot.items():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        except OSError:
            pass


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


def _clave_relacion(fila: Mapping[str, object]) -> tuple[str, str, str, str, str]:
    return (
        _texto(fila.get("id_curso")),
        _texto(fila.get("id_silabo")),
        _texto(fila.get("id_competencia")),
        _texto(fila.get("id_habilidad")),
        _texto(fila.get("id_herramienta")),
    )


def _fila_canonica_relacion(fila: Mapping[str, object]) -> dict[str, str]:
    return {columna: _texto(fila.get(columna)) for columna in COBERTURA_SCHEMA}


def _fusionar_relaciones(
    relaciones_enriquecidas: Sequence[Mapping[str, object]],
    relaciones_canonicas: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Update canonical columns without discarding enriched JSONL rows."""

    resultado = [dict(fila) for fila in relaciones_enriquecidas]
    por_clave: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = {}
    for fila in resultado:
        por_clave.setdefault(_clave_relacion(fila), []).append(fila)
    for relacion in relaciones_canonicas:
        canonica = _fila_canonica_relacion(relacion)
        coincidencias = por_clave.get(_clave_relacion(canonica), [])
        if coincidencias:
            for enriquecida in coincidencias:
                enriquecida.update(canonica)
            continue
        resultado.append(canonica)
        por_clave[_clave_relacion(canonica)] = [resultado[-1]]
    return resultado


def _preservar_relaciones_enriquecidas(
    relaciones_persistidas: Sequence[Mapping[str, object]],
    relaciones_actualizadas: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Merge current coverage without removing retained or new lineage."""

    resultado = [dict(fila) for fila in relaciones_persistidas]
    por_clave: dict[tuple[str, str, str, str, str], list[dict[str, object]]] = {}
    for fila in resultado:
        por_clave.setdefault(_clave_relacion(fila), []).append(fila)
    for actualizada in relaciones_actualizadas:
        coincidencias = por_clave.get(_clave_relacion(actualizada), [])
        if not coincidencias:
            nueva = dict(actualizada)
            resultado.append(nueva)
            por_clave[_clave_relacion(nueva)] = [nueva]
            continue
        for persistida in coincidencias:
            persistida.update(_fila_canonica_relacion(actualizada))
            persistida.update(
                {
                    clave: valor
                    for clave, valor in actualizada.items()
                    if clave not in COBERTURA_SCHEMA
                    and _texto(valor)
                    and not _texto(persistida.get(clave))
                }
            )
    return resultado


def _lineage_relacion(
    fila: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]],
    identidad: Mapping[str, str],
    id_competencia: str,
    id_habilidad: str,
    id_herramienta: str,
) -> dict[str, str]:
    """Build stable lineage for an edge created during approval."""

    id_relacion_fuente = _texto(identidad.get("id_cob_curricular"))
    relacion_fuente = next(
        (
            relacion
            for relacion in fuentes.get("cobertura_curricular_fuente.jsonl", ())
            if _texto(relacion.get("id_cob_curricular")) == id_relacion_fuente
        ),
        None,
    )

    def pertenece_al_paquete(item: Mapping[str, object]) -> bool:
        return all(
            _texto(item.get(clave)) == identidad[clave]
            for clave in (
                "id_ejecucion",
                "carrera",
                "periodo",
                "id_curso",
                "id_silabo",
                "id_habilidad_fuente",
            )
        )

    def id_fuente(nombre: str, nombre_canonico: str, id_canonico: str) -> str:
        if (
            isinstance(relacion_fuente, Mapping)
            and _texto(relacion_fuente.get(nombre_canonico)) == id_canonico
        ):
            return _texto(relacion_fuente.get(nombre_canonico.replace("_canonica", "_fuente")))
        for candidata in fuentes[nombre]:
            if (
                pertenece_al_paquete(candidata)
                and _texto(candidata.get(nombre_canonico)) == id_canonico
            ):
                return _texto(candidata.get(nombre_canonico.replace("_canonica", "_fuente")))
        return _texto(fila.get(nombre_canonico.replace("_canonica", "_fuente")))

    return {
        "id_ejecucion": identidad["id_ejecucion"],
        "id_relacion_fuente": id_relacion_fuente,
        "id_logro": _texto(fila.get("id_logro")),
        "id_competencia_fuente": id_fuente(
            "competencias_fuente.jsonl", "id_competencia_canonica", id_competencia
        ),
        "id_habilidad_fuente": id_fuente(
            "habilidades_fuente.jsonl", "id_habilidad_canonica", id_habilidad
        )
        or identidad["id_habilidad_fuente"],
        "id_herramienta_fuente": id_fuente(
            "herramientas_fuente.jsonl", "id_herramienta_canonica", id_herramienta
        )
        if id_herramienta
        else "",
        "id_competencia_canonica": id_competencia,
        "id_habilidad_canonica": id_habilidad,
        "id_herramienta_canonica": id_herramienta,
        "source_ref": _texto(fila.get("source_ref"))
        or _texto(fila.get("archivo"))
        or identidad["id_silabo"],
    }


def _cargar_archivos_curriculares(
    salida: Path, *, invalid_error: ExceptionFactory
) -> dict[str, list[dict[str, str]]]:
    archivos: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in ARCHIVOS_SALIDA:
        ruta = salida / nombre
        filas: list[dict[str, str]] = []
        if ruta.is_file():
            with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
                lector = csv.DictReader(archivo)
                if tuple(lector.fieldnames or ()) != columnas:
                    raise invalid_error(
                        f"El esquema de {nombre} no coincide con la salida curricular."
                    )
                filas = [
                    {columna: str(fila.get(columna) or "") for columna in columnas}
                    for fila in lector
                ]
        archivos[nombre] = filas
    return archivos


def _cargar_candidatos(
    reportes: Path, *, invalid_error: ExceptionFactory
) -> dict[str, list[dict[str, str]]] | None:
    """Load the candidate package without treating it as public CSV output."""

    ruta = reportes / CANDIDATOS_ARCHIVO
    if not ruta.is_file():
        return None
    try:
        contenido = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise invalid_error(f"Reporte de candidatos curriculares inválido: {ruta.name}.") from exc
    if not isinstance(contenido, dict) or not isinstance(contenido.get("archivos"), dict):
        raise invalid_error("El reporte de candidatos curriculares no es válido.")
    resultado: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in ARCHIVOS_SALIDA:
        filas = contenido["archivos"].get(nombre, [])
        if not isinstance(filas, list):
            raise invalid_error(f"Los candidatos de {nombre} no tienen una lista válida.")
        resultado[nombre] = [
            {columna: str(fila.get(columna) or "") for columna in columnas}
            for fila in filas
            if isinstance(fila, dict)
        ]
    return resultado


def _cargar_fuentes(
    reportes: Path, *, invalid_error: ExceptionFactory
) -> dict[str, list[dict[str, object]]]:
    return {
        nombre: _leer_jsonl(reportes / nombre, invalid_error=invalid_error)
        for nombre in (
            "competencias_fuente.jsonl",
            "habilidades_fuente.jsonl",
            "herramientas_fuente.jsonl",
            "cobertura_curricular_fuente.jsonl",
        )
    }


def _cargar_relaciones(
    salida: Path, reportes: Path, *, invalid_error: ExceptionFactory
) -> list[dict[str, object]]:
    relaciones_enriquecidas = _leer_jsonl(
        reportes / "cobertura_curricular_canonica.jsonl", invalid_error=invalid_error
    )
    ruta = salida / "cobertura_curricular.csv"
    if ruta.is_file():
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            return _fusionar_relaciones(
                relaciones_enriquecidas,
                [
                    {columna: str(fila.get(columna) or "") for columna in COBERTURA_SCHEMA}
                    for fila in lector
                ],
            )
    return relaciones_enriquecidas


def _escribir_archivos_curriculares(
    salida: Path, archivos: dict[str, list[dict[str, str]]]
) -> None:
    for nombre, columnas in ARCHIVOS_SALIDA:
        filas = archivos[nombre]
        filas.sort(
            key=lambda fila: tuple(clave_concepto(fila.get(columna, "")) for columna in columnas)
        )
        _escribir_csv_atomico(salida / nombre, columnas, filas)


def _eliminar_archivos_curriculares(salida: Path, *, not_permitted_error: ExceptionFactory) -> None:
    """Remove stale canonical files while an approval batch is unresolved."""

    for nombre, _ in ARCHIVOS_SALIDA:
        ruta = salida / nombre
        try:
            ruta.unlink(missing_ok=True)
        except OSError as exc:
            raise not_permitted_error(
                f"No se pudo retirar el CSV canónico pendiente: {nombre}."
            ) from exc


def _escribir_candidatos(
    reportes: Path,
    archivos: dict[str, list[dict[str, str]]],
    *,
    materialized: bool,
    paquetes: list[dict[str, object]] | None = None,
) -> None:
    """Persist the full candidate package beside CSV materialization."""

    contenido = {
        "version": "curricular-candidates/v1",
        "materialized": materialized,
        "archivos": {nombre: list(archivos[nombre]) for nombre, _ in ARCHIVOS_SALIDA},
        "paquetes": list(paquetes or []),
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


def _escribir_relaciones(
    salida: Path,
    reportes: Path,
    relaciones: list[dict[str, object]],
    *,
    invalid_error: ExceptionFactory,
) -> None:
    relaciones_enriquecidas = _preservar_relaciones_enriquecidas(
        _leer_jsonl(reportes / "cobertura_curricular_canonica.jsonl", invalid_error=invalid_error),
        relaciones,
    )
    relaciones_enriquecidas.sort(
        key=lambda fila: tuple(_texto(fila.get(columna)) for columna in COBERTURA_SCHEMA)
    )
    _escribir_jsonl_atomico(
        reportes / "cobertura_curricular_canonica.jsonl",
        relaciones_enriquecidas,
    )


def _leer_jsonl(ruta: Path, *, invalid_error: ExceptionFactory) -> list[dict[str, object]]:
    if not ruta.is_file():
        return []
    filas: list[dict[str, object]] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            valor = json.loads(linea)
        except json.JSONDecodeError as exc:
            raise invalid_error(f"Reporte JSONL inválido: {ruta.name}.") from exc
        if isinstance(valor, dict):
            filas.append(valor)
    return filas


def _leer_descartes(ruta: Path, *, invalid_error: ExceptionFactory) -> dict[str, dict[str, object]]:
    return {
        _texto(fila.get("package_id")): fila
        for fila in _leer_jsonl(ruta, invalid_error=invalid_error)
        if _texto(fila.get("package_id"))
    }


def _leer_decisiones(
    ruta: Path, *, invalid_error: ExceptionFactory
) -> dict[str, dict[str, object]]:
    return {
        _texto(fila.get("id_pendiente")): fila
        for fila in _leer_jsonl(ruta, invalid_error=invalid_error)
        if _texto(fila.get("id_pendiente"))
    }


def _append_decisiones(ruta: Path, filas: list[dict[str, object]]) -> None:
    if not filas:
        return
    with ruta.open("a", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")) + "\n")
        archivo.flush()


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


def _escribir_jsonl_atomico(ruta: Path, filas: Iterable[Mapping[str, object]]) -> None:
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
        "COB_CUR": "COB_CUR",
    }
    prefijo = prefijos.get(tipo, tipo)
    return hashed(prefijo, *partes)


def _clave_ruta(valor: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", valor).strip("_").upper()


def _texto(valor: Any) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()


def _mapping(valor: object) -> Mapping[str, object]:
    return valor if isinstance(valor, Mapping) else {}
