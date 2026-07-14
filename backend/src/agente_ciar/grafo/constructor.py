"""Construye el StateGraph del agente CIAR sin conectar servicios durante el import."""

from __future__ import annotations

from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from agente_ciar.grafo.enrutado import (
    ruta_tras_ejecutar,
    ruta_tras_estrategia,
    ruta_tras_pregunta,
    ruta_tras_validar,
)
from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.nodos.analiza_resultado import AnalizaResultado
from agente_ciar.nodos.devuelve_resultado import DevuelveResultado
from agente_ciar.nodos.ejecuta_cypher import EjecutaCypher
from agente_ciar.nodos.genera_cypher import GeneraCypher
from agente_ciar.nodos.obtiene_grafo import ObtieneGrafo
from agente_ciar.nodos.obtiene_pregunta import ObtienePregunta
from agente_ciar.nodos.resuelve_entidad import ResuelveEntidad
from agente_ciar.nodos.selecciona_estrategia import SeleccionaEstrategia
from agente_ciar.nodos.valida_cypher import ValidaCypher


def construir_grafo() -> Any:
    """Registra los nueve nodos y compila sus rutas acotadas."""
    builder = StateGraph(EstadoAgente)

    # Cada paso se instancia una vez; los clientes LLM permanecen perezosos hasta ser usados.
    # LangGraph acepta objetos invocables, aunque sus stubs no modelan clases con ``__call__``.
    builder.add_node("obtiene_pregunta", cast(Any, ObtienePregunta()))
    builder.add_node("obtiene_grafo", cast(Any, ObtieneGrafo()))
    builder.add_node("selecciona_estrategia", cast(Any, SeleccionaEstrategia()))
    builder.add_node("resuelve_entidad", cast(Any, ResuelveEntidad()))
    builder.add_node("genera_cypher", cast(Any, GeneraCypher()))
    builder.add_node("valida_cypher", cast(Any, ValidaCypher()))
    builder.add_node("ejecuta_cypher", cast(Any, EjecutaCypher()))
    builder.add_node("analiza_resultado", cast(Any, AnalizaResultado()))
    builder.add_node("devuelve_resultado", cast(Any, DevuelveResultado()))

    # La entrada segura continúa al schema; saludos y rechazos saltan directamente al cierre.
    builder.add_edge(START, "obtiene_pregunta")
    builder.add_conditional_edges(
        "obtiene_pregunta",
        ruta_tras_pregunta,
        {"obtiene_grafo": "obtiene_grafo", "devuelve_resultado": "devuelve_resultado"},
    )
    builder.add_edge("obtiene_grafo", "selecciona_estrategia")
    builder.add_conditional_edges(
        "selecciona_estrategia",
        ruta_tras_estrategia,
        {
            "analiza_resultado": "analiza_resultado",
            "valida_cypher": "valida_cypher",
            "resuelve_entidad": "resuelve_entidad",
        },
    )

    # Solo la rama dinámica necesita extracción y generación con OpenAI.
    builder.add_edge("resuelve_entidad", "genera_cypher")
    builder.add_edge("genera_cypher", "valida_cypher")
    builder.add_conditional_edges(
        "valida_cypher",
        ruta_tras_validar,
        {
            "ejecuta_cypher": "ejecuta_cypher",
            "genera_cypher": "genera_cypher",
            "devuelve_resultado": "devuelve_resultado",
        },
    )
    builder.add_conditional_edges(
        "ejecuta_cypher",
        ruta_tras_ejecutar,
        {
            "analiza_resultado": "analiza_resultado",
            "genera_cypher": "genera_cypher",
            "devuelve_resultado": "devuelve_resultado",
        },
    )

    # Toda rama termina preparando una respuesta y el proceso queda listo para otro mensaje.
    builder.add_edge("analiza_resultado", "devuelve_resultado")
    builder.add_edge("devuelve_resultado", END)
    # La memoria conversacional tiene TTL propio; un checkpointer en RAM duplicaría el estado
    # y crecería indefinidamente en un servidor con muchos identificadores de sesión.
    return builder.compile()
