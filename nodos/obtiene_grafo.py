"""
Nodo 2: obtiene_grafo

Pone en el estado el "schema" del grafo (que tipos de nodos, relaciones y propiedades
existen), en formato texto, para que los nodos que usan el LLM sepan con que trabajar.

La introspeccion real esta cacheada en utils/neo4j.py, asi que aunque este nodo se
ejecute en cada pregunta, solo se consulta Neo4j la primera vez (luego usa la cache).
"""
from __future__ import annotations

from estado import EstadoAgente
from nodos.nodo import Nodo
# Funcion que arma el schema en texto (vive en utils, reutilizada del codigo original).
from utils.neo4j import construir_schema_texto


class ObtieneGrafo(Nodo):
    """Carga el schema del grafo (en texto) dentro del estado."""

    nombre = "obtiene_grafo"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Construimos (o recuperamos de cache) el schema en texto.
        schema_texto = construir_schema_texto()
        # Lo guardamos en el estado para los siguientes nodos.
        return {"schema_texto": schema_texto}
