"""
Nodo 6: ejecuta_cypher  (no usa LLM)

Toma el Cypher ya validado y lo ejecuta en Neo4j (solo lectura). Guarda las filas
que devuelve la base en el estado. Si la ejecucion falla, guarda el error.
"""
from __future__ import annotations

from estado import EstadoAgente
from nodos.nodo import Nodo
from utils.neo4j import ejecutar_lectura


class EjecutaCypher(Nodo):
    """Ejecuta la consulta Cypher en Neo4j y guarda las filas resultantes."""

    nombre = "ejecuta_cypher"

    def __call__(self, estado: EstadoAgente) -> dict:
        cypher = estado.get("cypher", "")
        try:
            # Ejecutamos la consulta de lectura y obtenemos una lista de diccionarios.
            filas = ejecutar_lectura(cypher)
            # Guardamos las filas en el estado (vacio si no hubo resultados).
            return {"filas": filas}
        except Exception as exc:
            # Si Neo4j devuelve un error (ej. sintaxis), lo guardamos para informarlo.
            return {"filas": [], "error": f"Error al ejecutar en Neo4j: {exc}"}
