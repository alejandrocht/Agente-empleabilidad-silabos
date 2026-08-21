#!/usr/bin/env python3
"""Minimal interactive console for the current async CIAR graph API."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Allow running this script directly from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# In interactive mode we want the human-readable verbose trace; keep the
# structured operational logs quiet unless the user explicitly configured them.
os.environ.setdefault("CIAR_LOG_LEVEL", "WARNING")

from agente.grafo.constructor import responder


async def run_console() -> None:
    """Read questions and invoke the current async graph entry point."""
    print("Agente CIAR")
    print("Escribe tu pregunta. Comando para salir: /salir\n")

    while True:
        try:
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not pregunta:
            continue
        if pregunta.lower() == "/salir":
            break

        try:
            respuesta = await responder(pregunta, verbose=True)
        except Exception as exc:
            print(f"\nError del agente ({type(exc).__name__}). Intenta nuevamente.\n")
            continue

        print(f"\n[Respuesta] {respuesta}\n")

    print("Listo.")


def main() -> None:
    """Start the async console loop."""
    asyncio.run(run_console())


if __name__ == "__main__":
    main()
