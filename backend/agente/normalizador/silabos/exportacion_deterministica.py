"""Consolida todas las carreras de un directorio de sílabos en cinco CSV, sin LLM."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from agente.normalizador.silabos.extraccion_curricular import _extraer_docx, _hash_id
from agente.normalizador.silabos.salida_catalogos import (
    ARCHIVOS_CATALOGO,
    construir_catalogos_curriculares,
)

ARCHIVOS = tuple(nombre for nombre, _ in ARCHIVOS_CATALOGO if nombre != "catalogo_habilidades.csv")
ESQUEMAS: dict[str, tuple[str, ...]] = dict(ARCHIVOS_CATALOGO)
CLAVES = {
    "curso.csv": "id_curso",
    "silabo.csv": "id_silabo",
    "catalogo_competencias.csv": "id_competencia",
    "catalogo_logros.csv": "id_logro",
    "cobertura_curricular.csv": "id_cobertura_curricular",
}


def exportar(origen: Path, salida: Path) -> dict[str, object]:
    """Usa solo las competencias y referencias a logros declaradas en cada DOCX."""
    if not origen.is_dir():
        raise ValueError(f"No existe el directorio de sílabos: {origen}")
    carreras = [
        carpeta
        for carpeta in sorted(origen.iterdir())
        if carpeta.is_dir()
        and not carpeta.name.startswith(".")
        and carpeta.name not in {"silabs_errores", "ESTUDIOS_GENERALES"}
    ]
    acumulados: dict[str, dict[str, dict[str, str]]] = {nombre: {} for nombre in ARCHIVOS}
    procesados = 0
    carreras_procesadas = 0
    with TemporaryDirectory() as temporal:
        for carpeta in carreras:
            for periodo_dir in sorted(carpeta.iterdir()):
                if not periodo_dir.is_dir():
                    continue
                documentos = sorted(
                    ruta
                    for ruta in periodo_dir.rglob("*.docx")
                    if not ruta.name.startswith((".", "~$"))
                )
                if not documentos:
                    continue
                registros = []
                for ruta in documentos:
                    nombre = ruta.relative_to(periodo_dir).as_posix()
                    try:
                        registro = _extraer_docx(ruta, nombre, carpeta.name, periodo_dir.name)
                    except Exception as exc:
                        raise ValueError(f"No se pudo extraer {ruta}: {exc}") from exc
                    # El código puede repetirse incluso entre dos cursos de una misma
                    # carrera; el archivo de origen identifica inequívocamente al curso.
                    registro["id_curso"] = _hash_id("CUR", carpeta.name, periodo_dir.name, nombre)
                    registro["id_silabo"] = _hash_id("SIL", carpeta.name, periodo_dir.name, nombre)
                    registros.append(registro)
                lote = Path(temporal) / carpeta.name / periodo_dir.name
                construir_catalogos_curriculares(
                    registros, lote, carrera=carpeta.name, periodo_academico=periodo_dir.name
                )
                for nombre in ARCHIVOS:
                    with (lote / nombre).open(encoding="utf-8-sig", newline="") as archivo:
                        for fila in csv.DictReader(archivo):
                            identificador = fila[CLAVES[nombre]]
                            anterior = acumulados[nombre].setdefault(identificador, fila)
                            if anterior != fila:
                                if nombre != "catalogo_competencias.csv":
                                    raise ValueError(f"ID ambiguo en {nombre}: {identificador}")
                                acumulados[nombre][identificador] = min(
                                    (anterior, fila),
                                    key=lambda valor: tuple(
                                        valor[campo] for campo in sorted(valor)
                                    ),
                                )
                procesados += len(documentos)
                carreras_procesadas += 1
                print(f"{carpeta.name}/{periodo_dir.name}: {len(documentos)} sílabos", flush=True)

    if not procesados:
        raise ValueError(f"No se encontraron sílabos DOCX en {origen}")
    salida.mkdir(parents=True, exist_ok=True)
    for nombre in ARCHIVOS:
        with (salida / nombre).open("w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=ESQUEMAS[nombre])
            escritor.writeheader()
            escritor.writerows(acumulados[nombre][clave] for clave in sorted(acumulados[nombre]))
    return {
        "carreras": carreras_procesadas,
        "silabos_fuente": procesados,
        "archivos": {nombre: len(acumulados[nombre]) for nombre in ARCHIVOS},
        "salida": str(salida),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origen", type=Path)
    parser.add_argument("salida", type=Path)
    args = parser.parse_args()
    print(json.dumps(exportar(args.origen, args.salida), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
