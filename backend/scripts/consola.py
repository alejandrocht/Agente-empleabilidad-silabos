#!/usr/bin/env python3
"""Punto de entrada interactivo del agente CIAR v2."""

from __future__ import annotations

import uuid
from typing import Any

from agente_ciar.config import settings as _settings  # noqa: F401
from agente_ciar.grafo.constructor import construir_grafo
from agente_ciar.observabilidad.logger import log_fin_turno


def run_console() -> None:
    """Mantiene una sesión y muestra cada nodo, Cypher y respuesta del turno."""
    grafo = construir_grafo()
    id_sesion = f"ciar-console-{uuid.uuid4().hex[:8]}"
    print("Agente CIAR consola v2")
    print("Escribe tu pregunta. Comando para salir: /salir\n")

    while True:
        try:
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pregunta:
            continue
        if pregunta.lower() in {"/salir", "salir", "exit", "quit"}:
            break

        config = {"configurable": {"thread_id": id_sesion}, "recursion_limit": 20}
        estado_final: dict[str, Any] = {}
        pasos: list[str] = []
        try:
            print("  [Flujo] Iniciando recorrido...")
            for paso in grafo.stream(
                {"pregunta": pregunta, "id_sesion": id_sesion},
                config=config,
                stream_mode="updates",
            ):
                for nombre_nodo, cambios in paso.items():
                    pasos.append(nombre_nodo)
                    print(f"  [Flujo] {nombre_nodo}")
                    if cambios:
                        if cambios.get("cypher"):
                            print(f"  [Cypher] {cambios['cypher']}")
                        if cambios.get("error"):
                            print(f"  [Bloqueado] {cambios['error']}")
                        estado_final.update(cambios)
            respuesta = str(estado_final.get("respuesta", "(sin respuesta)"))
            log_fin_turno(id_sesion, respuesta, pasos)
            print(f"\n[Respuesta] {respuesta}\n")
        except Exception as exc:
            print(f"\nError del agente: {exc}\n")
    print("Listo.")


def main() -> None:
    """Arranca la consola después de que settings haya cargado el entorno."""
    run_console()


if __name__ == "__main__":
    main()
