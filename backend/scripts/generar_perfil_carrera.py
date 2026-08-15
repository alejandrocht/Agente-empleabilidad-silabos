"""Crea un perfil curricular bootstrap desde una ejecución ya validada."""

from __future__ import annotations

import argparse
from pathlib import Path

from agente.normalizador.silabos.perfiles import crear_perfil_bootstrap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ejecucion", type=Path, required=True)
    parser.add_argument("--catalogos", type=Path, required=True)
    parser.add_argument("--carrera", required=True)
    parser.add_argument("--periodo", required=True)
    parser.add_argument("--reemplazar", action="store_true")
    argumentos = parser.parse_args()

    perfil = crear_perfil_bootstrap(
        argumentos.ejecucion,
        argumentos.catalogos,
        argumentos.carrera,
        argumentos.periodo,
        reemplazar=argumentos.reemplazar,
    )
    print(
        f"Perfil bootstrap creado en {perfil.directorio} "
        f"(competencias={perfil.competencias}, habilidades={perfil.habilidades}, "
        f"herramientas={perfil.herramientas}, pendientes={perfil.habilidades_pendientes})."
    )


if __name__ == "__main__":
    main()
