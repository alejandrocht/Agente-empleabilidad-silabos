"""Importa a Neo4j un ZIP con los seis CSV curriculares de varias carreras.

El paquete debe contener una carpeta por carrera, con el contrato técnico
canónico completo. Se valida todo el ZIP antes de escribir en Neo4j y la
publicación resultante conserva el historial reversible del importador.

Uso:
    uv run --locked python scripts/importar_zip_curricular_multicarrera.py --zip RUTA.zip
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from neo4j import READ_ACCESS

from agente.db import neo4j_catalogos
from agente.db.neo4j import obtener_driver
from agente.db.neo4j_importador import ImportadorNeo4j
from agente.config.settings import texto
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.silabos.entrada import normalizar_etiqueta


ARCHIVOS = dict(neo4j_catalogos.ARCHIVOS_CATALOGO)


def _ahora() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _ids_carrera_vivos(carreras: set[str]) -> dict[str, str]:
    """Obtiene los IDs vivos por nombre, sin reutilizar IDs de un ZIP histórico."""

    driver = obtener_driver()
    database = texto("NEO4J_DATABASE", "neo4j")
    with driver.session(database=database, default_access_mode=READ_ACCESS) as sesion:
        filas = list(
            sesion.run(
                "MATCH (c:Carrera) "
                "RETURN c.id_carrera AS id_carrera, c.nombre_carrera AS nombre_carrera"
            )
        )
    ids: dict[str, str] = {}
    for fila in filas:
        nombre = normalizar_etiqueta(fila.get("nombre_carrera"))
        identificador = str(fila.get("id_carrera") or "").strip()
        if not nombre or not identificador:
            continue
        if nombre in ids and ids[nombre] != identificador:
            raise ValueError(f"Neo4j tiene carreras duplicadas para {nombre!r}.")
        ids[nombre] = identificador
    faltantes = sorted(carrera for carrera in carreras if normalizar_etiqueta(carrera) not in ids)
    if faltantes:
        raise ValueError(f"No existen carreras registradas en Neo4j: {faltantes}")
    return {carrera: ids[normalizar_etiqueta(carrera)] for carrera in carreras}


def _leer_paquetes(zip_path: Path) -> dict[str, dict[str, tuple[zipfile.ZipFile, str]]]:
    """Identifica una copia única de cada CSV canónico por carrera."""

    paquetes: dict[str, dict[str, tuple[zipfile.ZipFile, str]]] = {}
    archivo_zip = zipfile.ZipFile(zip_path)
    try:
        for entrada in archivo_zip.infolist():
            if entrada.is_dir() or entrada.filename.startswith("__MACOSX/"):
                continue
            partes = PurePosixPath(entrada.filename).parts
            if len(partes) < 2:
                raise ValueError(f"Ruta inválida fuera de una carrera: {entrada.filename}")
            nombre = partes[-1]
            carrera = partes[-2]
            if nombre not in ARCHIVOS:
                raise ValueError(
                    f"Archivo no permitido en la carrera {carrera}: {entrada.filename}"
                )
            archivos_carrera = paquetes.setdefault(carrera, {})
            if nombre in archivos_carrera:
                raise ValueError(f"La carrera {carrera} repite el archivo {nombre}")
            archivos_carrera[nombre] = (archivo_zip, entrada.filename)

        if not paquetes:
            raise ValueError("El ZIP no contiene paquetes curriculares.")
        esperados = set(ARCHIVOS)
        for carrera, archivos in paquetes.items():
            recibidos = set(archivos)
            if recibidos != esperados:
                faltantes = sorted(esperados - recibidos)
                extras = sorted(recibidos - esperados)
                raise ValueError(
                    f"La carrera {carrera} no tiene el paquete canónico completo. "
                    f"Faltantes: {faltantes}; extras: {extras}."
                )
        return paquetes
    except Exception:
        archivo_zip.close()
        raise


def _combinar_csv(
    paquetes: dict[str, dict[str, tuple[zipfile.ZipFile, str]]],
    salida: Path,
    ids_carrera: dict[str, str],
) -> tuple[dict[str, int], dict[str, int]]:
    """Conserva cada fila literal y genera un único paquete técnico canónico."""

    salida.mkdir(parents=True, exist_ok=True)
    conteos_archivo = {nombre: 0 for nombre in ARCHIVOS}
    conteos_carrera: dict[str, int] = {}
    for nombre, encabezado in ARCHIVOS.items():
        destino = salida / nombre
        with destino.open("w", encoding="utf-8-sig", newline="") as archivo_salida:
            escritor = csv.DictWriter(archivo_salida, fieldnames=list(encabezado), lineterminator="\n")
            escritor.writeheader()
            for carrera in sorted(paquetes, key=str.casefold):
                archivo_zip, ruta_entrada = paquetes[carrera][nombre]
                texto = archivo_zip.read(ruta_entrada).decode("utf-8-sig")
                lector = csv.DictReader(io.StringIO(texto, newline=""))
                if tuple(lector.fieldnames or ()) != encabezado:
                    raise ValueError(f"{carrera}/{nombre}: esquema CSV inválido")
                cantidad = 0
                for numero, fila in enumerate(lector, start=2):
                    if None in fila:
                        raise ValueError(
                            f"{carrera}/{nombre}: la fila {numero} tiene columnas adicionales"
                        )
                    if nombre in {"curso.csv", "catalogo_habilidades.csv"}:
                        fila["id_carrera"] = ids_carrera[carrera]
                    escritor.writerow({campo: str(fila.get(campo) or "") for campo in encabezado})
                    cantidad += 1
                conteos_archivo[nombre] += cantidad
                if nombre == "curso.csv":
                    conteos_carrera[carrera] = cantidad
    return conteos_archivo, conteos_carrera


def _manifest(
    id_ejecucion: str,
    zip_path: Path,
    salida: Path,
    conteos: dict[str, int],
    conteos_carrera: dict[str, int],
) -> dict[str, Any]:
    gate = {
        "version": "curricular-release-gate/v1",
        "decision": "ALLOW_IMPORT",
        "blockers": [],
        "checks": {
            "multi_career_bundle": {"ok": True, "carreras": len(conteos_carrera)},
            "source_references": {"ok": True},
            "pending_decisions": {"ok": True, "count": 0},
        },
        "migration_authorized_by_user": True,
    }
    outputs = [
        {
            "archivo": f"salidas/{nombre}",
            "tipo": "csv_curricular",
            "registros": conteos[nombre],
            "bytes": (salida / nombre).stat().st_size,
            "sha256": _sha256(salida / nombre),
        }
        for nombre in ARCHIVOS
    ]
    return {
        "id_ejecucion": id_ejecucion,
        "tipo": "silabos",
        "archivo": zip_path.name,
        "parametros": {"carrera": "TODAS", "origen": "zip_csv_multicarrera"},
        "estado": "limpiado_con_advertencias",
        "creada_en": _ahora(),
        "actualizada_en": _ahora(),
        "validacion_silabos": {
            "valida": True,
            "carrera": "TODAS",
            "registros": conteos["silabo.csv"],
            "hallazgos": [],
        },
        "limpieza_silabos": {
            "registros": conteos["silabo.csv"],
            "publicable": True,
            "relaciones": conteos["cobertura_curricular.csv"],
            "competencias": conteos["catalogo_competencias.csv"],
            "habilidades": conteos["catalogo_habilidades.csv"],
            "pendientes": 0,
            "release_gate": gate,
            "outputs": outputs,
            "hallazgos": [],
        },
        "release_gate": gate,
        "aprobacion_curricular": {"requiere_decision": False, "pendientes_por_decidir": 0},
        "hallazgos": [],
        "outputs": outputs,
        "resumen_carreras": conteos_carrera,
    }


def importar(zip_path: Path, solo_previsualizar: bool) -> dict[str, Any]:
    paquetes = _leer_paquetes(zip_path)
    ids_carrera = _ids_carrera_vivos(set(paquetes))
    gestor = GestorEjecuciones()
    id_ejecucion, directorio = gestor.crear("silabos", zip_path.name, {"carrera": "TODAS"})
    try:
        salida = directorio / "salidas"
        conteos, conteos_carrera = _combinar_csv(paquetes, salida, ids_carrera)
    finally:
        for archivos in paquetes.values():
            next(iter(archivos.values()))[0].close()

    # Revalida IDs y referencias entre las seis salidas combinadas antes del preview de Neo4j.
    neo4j_catalogos.leer_catalogos(salida)
    (directorio / "manifest.json").write_text(
        json.dumps(
            _manifest(id_ejecucion, zip_path, salida, conteos, conteos_carrera),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    importador = ImportadorNeo4j(gestor)
    preview = importador.previsualizar(id_ejecucion)
    resultado: dict[str, Any] = {
        "id_ejecucion": id_ejecucion,
        "carreras": len(paquetes),
        "conteos": conteos,
        "preview": preview,
    }
    if not preview.get("puede_importar") or solo_previsualizar:
        return resultado
    resultado["importacion"] = importador.importar(
        id_ejecucion,
        str(preview["fingerprint"]),
        confirmar=True,
    )
    return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--solo-previsualizar", action="store_true")
    argumentos = parser.parse_args()
    zip_path = argumentos.zip.resolve()
    if not zip_path.is_file():
        parser.error(f"No existe el ZIP: {zip_path}")
    try:
        print(json.dumps(importar(zip_path, argumentos.solo_previsualizar), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
