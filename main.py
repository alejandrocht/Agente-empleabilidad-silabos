#!/usr/bin/env python3
"""
main.py — punto de entrada del agente CIAR.

Arranca la consola: carga la configuracion, construye el grafo y se queda en un bucle
leyendo preguntas del usuario, ejecutando el grafo y mostrando la respuesta.

Uso:
  python main.py
Comandos dentro de la consola:
  /salir   -> termina
"""
from __future__ import annotations

import uuid

# Cargamos la configuracion del .env (claves de LLM y Neo4j).
from utils.config import cargar_entorno
# Funciones para construir el grafo y exportar su diagrama.
from agent import construir_grafo, guardar_mermaid
# El mensaje de usuario que metemos al grafo.
from langchain_core.messages import HumanMessage


def run_console() -> None:
    """Bucle principal de la consola: lee preguntas y muestra respuestas."""
    # Construimos el grafo una sola vez (al inicio).
    grafo = construir_grafo()
    # Guardamos el diagrama del grafo (opcional, util para visualizarlo).
    guardar_mermaid(grafo)

    # Un id unico para esta sesion (lo usa la memoria del grafo).
    id_sesion = f"ciar-console-{uuid.uuid4().hex[:8]}"

    # Mensaje de bienvenida.
    print("Agente CIAR consola (version modular)")
    print("Escribe tu pregunta. Comando para salir: /salir\n")

    # Bucle infinito: se repite hasta que el usuario decida salir.
    while True:
        try:
            # Leemos lo que el usuario escribe despues del ">".
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            # Si el usuario presiona Ctrl+C / Ctrl+D, salimos limpio.
            print()
            break

        # Si no escribio nada, volvemos a preguntar.
        if not pregunta:
            continue
        # Comandos para salir.
        if pregunta.lower() in {"/salir", "salir", "exit", "quit"}:
            break

        # Configuracion de la corrida: el thread_id agrupa la conversacion por sesion.
        config = {
            "configurable": {"thread_id": id_sesion},
            # Limite de pasos para evitar bucles infinitos (nuestro flujo usa ~8).
            "recursion_limit": 15,
        }

        # Estado inicial: solo metemos la pregunta. Los nodos van llenando el resto.
        entrada = {"pregunta": pregunta}

        try:
            # Ejecutamos el grafo paso a paso y mostramos por que nodo va pasando.
            print("  [Flujo] Iniciando recorrido por los nodos...")
            estado_final = {}
            for paso in grafo.stream(entrada, config=config, stream_mode="updates"):
                # paso es un dict {nombre_nodo: cambios_que_hizo}.
                for nombre_nodo, cambios in paso.items():
                    print(f"  [Flujo] Paso por el nodo: '{nombre_nodo}'")
                    # Vamos acumulando los cambios para tener el estado final.
                    if cambios:
                        estado_final.update(cambios)

            # Mostramos la respuesta final que quedo en el estado.
            print(f"\n{estado_final.get('respuesta', '(sin respuesta)')}\n")
        except Exception as exc:
            # Si algo explota, lo mostramos sin tumbar la consola.
            print(f"\nError del agente: {exc}\n")

    print("Listo.")


def main() -> None:
    # Primero cargamos la config, luego arrancamos la consola.
    cargar_entorno()
    run_console()


if __name__ == "__main__":
    main()
