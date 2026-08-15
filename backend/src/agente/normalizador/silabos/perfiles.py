"""Generación controlada de perfiles curriculares por carrera y periodo."""

from __future__ import annotations

import csv
import json
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from agente.normalizador.silabos.salida import ARCHIVOS_SALIDA


@dataclass(frozen=True, slots=True)
class PerfilBootstrap:
    """Resultado de materializar un perfil que aún requiere revisión humana."""

    directorio: Path
    competencias: int
    habilidades: int
    herramientas: int
    habilidades_pendientes: int


def crear_perfil_bootstrap(
    directorio_ejecucion: Path,
    directorio_catalogos: Path,
    carrera: str,
    periodo: str,
    *,
    reemplazar: bool = False,
) -> PerfilBootstrap:
    """Copia un resultado curricular validado como perfil bootstrap versionado.

    Los CSV conservan los mismos encabezados del contrato público. La condición
    de bootstrap y los casos pendientes viven fuera de esas tablas, dentro de
    un manifiesto y reportes JSONL auditables.
    """

    salida = directorio_ejecucion / "salidas"
    if not salida.is_dir():
        raise FileNotFoundError(f"No se encontraron salidas curriculares en {salida}")

    destino = directorio_catalogos / "carreras" / _clave_carrera(carrera) / _periodo(periodo)
    if destino.exists() and not reemplazar:
        raise FileExistsError(
            f"El perfil ya existe en {destino}; use reemplazar=True tras revisarlo."
        )
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)

    conteos: dict[str, int] = {}
    for nombre, columnas in ARCHIVOS_SALIDA:
        origen = salida / nombre
        if nombre == "cobertura_curricular.csv" and not origen.is_file():
            continue
        filas = _leer_y_validar_csv(origen, columnas)
        _escribir_csv(destino / nombre, columnas, filas)
        conteos[nombre] = len(filas)

    reportes_origen = salida / "reportes"
    pendientes = _filtrar_habilidades_pendientes(reportes_origen / "habilidades_fuente.jsonl")
    reportes_destino = destino / "reportes"
    reportes_destino.mkdir()
    _escribir_jsonl(reportes_destino / "habilidades_pendientes.jsonl", pendientes)
    for nombre in (
        "herramientas_fuente.jsonl",
        "competencias_fuente.jsonl",
        "decisiones_llm.jsonl",
        "analisis_llm.json",
    ):
        origen = reportes_origen / nombre
        if origen.is_file():
            shutil.copyfile(origen, reportes_destino / nombre)

    manifiesto = {
        "tipo": "bootstrap_silabos",
        "estado": "REQUIERE_REVISION_HUMANA",
        "carrera": _clave_carrera(carrera),
        "periodo": _periodo(periodo),
        "origen_ejecucion": directorio_ejecucion.name,
        "regla": (
            "Competencias declaradas por los sílabos; habilidades y herramientas "
            "solo con evidencia canónica o estructurada."
        ),
        "conteos": {
            "competencias": conteos.get("catalogo_competencias.csv", 0),
            "habilidades": conteos.get("catalogo_habilidades.csv", 0),
            "herramientas": conteos.get("catalogo_herramientas.csv", 0),
            "cobertura": conteos.get("cobertura_curricular.csv", 0),
            "habilidades_pendientes": len(pendientes),
        },
    }
    (destino / "perfil.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return PerfilBootstrap(
        destino,
        conteos.get("catalogo_competencias.csv", 0),
        conteos.get("catalogo_habilidades.csv", 0),
        conteos.get("catalogo_herramientas.csv", 0),
        len(pendientes),
    )


def _clave_carrera(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor)
    normalizado = "".join(
        caracter for caracter in normalizado if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^A-Za-z0-9]+", "_", normalizado).strip("_").upper()


def _periodo(valor: str) -> str:
    periodo = re.sub(r"[^0-9-]", "", valor)
    if not periodo:
        raise ValueError("El periodo es obligatorio para crear un perfil curricular.")
    return periodo


def _leer_y_validar_csv(ruta: Path, columnas: tuple[str, ...]) -> list[dict[str, str]]:
    if not ruta.is_file():
        raise FileNotFoundError(f"Falta el CSV requerido para el perfil: {ruta}")
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if tuple(lector.fieldnames or ()) != columnas:
            raise ValueError(f"El esquema de {ruta.name} no coincide con el contrato público.")
        return [
            {columna: str(fila.get(columna, "") or "") for columna in columnas}
            for fila in lector
        ]


def _escribir_csv(ruta: Path, columnas: tuple[str, ...], filas: list[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="raise")
        escritor.writeheader()
        escritor.writerows(filas)


def _filtrar_habilidades_pendientes(ruta: Path) -> list[dict[str, object]]:
    if not ruta.is_file():
        return []
    pendientes: list[dict[str, object]] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        fila = json.loads(linea)
        if isinstance(fila, dict) and fila.get("estado_resolucion") == "REVISAR":
            pendientes.append(fila)
    return pendientes


def _escribir_jsonl(ruta: Path, filas: list[dict[str, object]]) -> None:
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for fila in filas:
            archivo.write(json.dumps(fila, ensure_ascii=False, separators=(",", ":")))
            archivo.write("\n")
