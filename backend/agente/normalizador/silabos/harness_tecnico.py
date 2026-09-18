"""CLI for proposing technical competencies from one curricular execution."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from agente.config.settings import configuracion_normalizador_curricular

from .analista_tecnico import (
    cargar_catalogo_tecnico,
    escribir_propuestas_tecnicas,
    inferir_competencias_tecnicas,
)


def _leer_jsonl(ruta: Path) -> list[dict[str, object]]:
    registros: list[dict[str, object]] = []
    with ruta.open(encoding="utf-8") as archivo:
        for numero, linea in enumerate(archivo, start=1):
            if not linea.strip():
                continue
            try:
                valor = json.loads(linea)
            except json.JSONDecodeError as exc:
                raise ValueError(f"La línea {numero} no contiene JSON válido") from exc
            if not isinstance(valor, dict):
                raise ValueError(f"La línea {numero} no contiene un objeto JSON")
            registros.append(valor)
    return registros


def ejecutar(
    ruta_silabos: Path,
    ruta_catalogo: Path,
    ruta_salida: Path,
) -> dict[str, object]:
    """Run one career-period batch and persist only pending proposals."""

    registros = _leer_jsonl(ruta_silabos)
    alcances = {
        (str(registro.get("carrera") or ""), str(registro.get("periodo") or ""))
        for registro in registros
    }
    if len(alcances) > 1:
        raise ValueError("La ejecución no puede mezclar carreras o períodos")
    if not alcances or not all(alcance[0] and alcance[1] for alcance in alcances):
        raise ValueError("La ejecución requiere una carrera y un período")

    catalogo = cargar_catalogo_tecnico(ruta_catalogo)
    propuestas = inferir_competencias_tecnicas(
        registros,
        configuracion_normalizador_curricular(),
        catalogo,
    )
    escribir_propuestas_tecnicas(ruta_salida, propuestas)
    carrera, periodo = next(iter(alcances))
    return {
        "carrera": carrera,
        "periodo": periodo,
        "silabos": len(registros),
        "candidatos_catalogo": len(catalogo.para_carrera(carrera)),
        "propuestas_pendientes": len(propuestas),
        "salida": str(ruta_salida),
    }


def main(argumentos: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--silabos", type=Path, required=True, help="Input JSONL from the extractor"
    )
    parser.add_argument("--catalogo", type=Path, required=True, help="Career technical XLSX")
    parser.add_argument("--salida", type=Path, required=True, help="Pending proposals JSONL")
    args = parser.parse_args(argumentos)
    print(json.dumps(ejecutar(args.silabos, args.catalogo, args.salida), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
