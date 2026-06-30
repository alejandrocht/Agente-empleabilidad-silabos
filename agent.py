"""
agent.py — construye el grafo LangGraph del agente CIAR.

Aqui se "arma" el flujo: se registran los 8 nodos y se conectan con flechas.
El flujo es LINEAL, con un solo desvio: si valida_cypher detecta un error, se salta
la ejecucion y el analisis, y va directo a devolver el resultado (el error).

Flujo:
  START
    -> obtiene_pregunta
    -> obtiene_grafo
    -> resuelve_entidad
    -> genera_cypher
    -> valida_cypher --(si error)--> devuelve_resultado
    -> ejecuta_cypher
    -> analiza_resultado
    -> devuelve_resultado
    -> END
"""
from __future__ import annotations

from pathlib import Path

# Piezas de LangGraph para construir el grafo de estados.
from langgraph.graph import END, START, StateGraph
# MemorySaver guarda el historial en memoria (permite conversaciones por sesion).
from langgraph.checkpoint.memory import MemorySaver

# El tipo del estado que viaja entre nodos.
from estado import EstadoAgente

# Importamos cada nodo (cada uno es una clase que se comporta como funcion).
from nodos.obtiene_pregunta import ObtienePregunta
from nodos.obtiene_grafo import ObtieneGrafo
from nodos.resuelve_entidad import ResuelveEntidad
from nodos.genera_cypher import GeneraCypher
from nodos.valida_cypher import ValidaCypher
from nodos.ejecuta_cypher import EjecutaCypher
from nodos.analiza_resultado import AnalizaResultado
from nodos.devuelve_resultado import DevuelveResultado

# Ruta donde guardaremos el diagrama Mermaid del grafo (para visualizarlo).
RUTA_MERMAID = Path(__file__).resolve().parent / "langgraph_agent.mmd"


# Maximo de intentos de generar/corregir el Cypher antes de rendirse.
MAX_INTENTOS = 2


def _ruta_tras_validar(estado: EstadoAgente) -> str:
    """Decide el camino tras valida_cypher: ejecutar, reintentar o rendirse."""
    # Sin error: el Cypher es valido, lo ejecutamos.
    if not estado.get("error"):
        return "ejecuta_cypher"
    # Hay error pero quedan intentos: volvemos a generar (con el error como pista).
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return "genera_cypher"
    # Hay error y ya no quedan intentos: vamos a devolver el error.
    return "devuelve_resultado"


def _ruta_tras_ejecutar(estado: EstadoAgente) -> str:
    """Decide el camino tras ejecuta_cypher: analizar, reintentar o rendirse."""
    # Sin error: tenemos filas, pasamos a redactar la respuesta.
    if not estado.get("error"):
        return "analiza_resultado"
    # Error en ejecucion pero quedan intentos: volvemos a generar para corregir.
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return "genera_cypher"
    # Error y sin intentos: devolvemos el error.
    return "devuelve_resultado"


def construir_grafo():
    """Crea, conecta y compila el grafo del agente. Devuelve el grafo listo para usar."""
    # 1) Creamos el constructor del grafo, indicandole el tipo de estado.
    builder = StateGraph(EstadoAgente)

    # 2) Registramos cada nodo con un nombre. Creamos una instancia de cada clase.
    builder.add_node("obtiene_pregunta", ObtienePregunta())
    builder.add_node("obtiene_grafo", ObtieneGrafo())
    builder.add_node("resuelve_entidad", ResuelveEntidad())
    builder.add_node("genera_cypher", GeneraCypher())
    builder.add_node("valida_cypher", ValidaCypher())
    builder.add_node("ejecuta_cypher", EjecutaCypher())
    builder.add_node("analiza_resultado", AnalizaResultado())
    builder.add_node("devuelve_resultado", DevuelveResultado())

    # 3) Conectamos los nodos con flechas (el orden del flujo).
    builder.add_edge(START, "obtiene_pregunta")
    builder.add_edge("obtiene_pregunta", "obtiene_grafo")
    builder.add_edge("obtiene_grafo", "resuelve_entidad")
    builder.add_edge("resuelve_entidad", "genera_cypher")
    builder.add_edge("genera_cypher", "valida_cypher")

    # 3b) Tras validar: ejecutar (ok), reintentar generando (error con intentos) o rendirse.
    builder.add_conditional_edges(
        "valida_cypher",
        _ruta_tras_validar,
        {
            "ejecuta_cypher": "ejecuta_cypher",
            "genera_cypher": "genera_cypher",
            "devuelve_resultado": "devuelve_resultado",
        },
    )

    # 3c) Tras ejecutar: analizar (ok), reintentar (error con intentos) o rendirse.
    builder.add_conditional_edges(
        "ejecuta_cypher",
        _ruta_tras_ejecutar,
        {
            "analiza_resultado": "analiza_resultado",
            "genera_cypher": "genera_cypher",
            "devuelve_resultado": "devuelve_resultado",
        },
    )

    # 3d) Cierre del flujo.
    builder.add_edge("analiza_resultado", "devuelve_resultado")
    builder.add_edge("devuelve_resultado", END)

    # 4) Compilamos el grafo con memoria de conversacion.
    return builder.compile(checkpointer=MemorySaver())


def guardar_mermaid(grafo) -> None:
    """Exporta el diagrama del grafo a un archivo .mmd (para verlo en un visor Mermaid)."""
    RUTA_MERMAID.write_text(grafo.get_graph().draw_mermaid(), encoding="utf-8")
