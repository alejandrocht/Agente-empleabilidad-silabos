"""
Definicion del "estado" del agente.

En LangGraph, los nodos NO se pasan argumentos sueltos entre si. En su lugar, existe
un unico objeto compartido (el "estado") que viaja de nodo en nodo. Cada nodo lee del
estado lo que necesita y devuelve solo las claves que modifica.

Aqui definimos que campos tiene ese estado.
"""
from __future__ import annotations

# TypedDict permite describir un diccionario indicando que claves tiene y de que tipo.
from typing import TypedDict


class EstadoAgente(TypedDict, total=False):
    """Datos que viajan entre los nodos del grafo. (total=False = todos opcionales)."""

    # La pregunta original del usuario (texto en espanol).
    pregunta: str

    # El schema del grafo en texto, para darselo al LLM. Lo llena obtiene_grafo.
    schema_texto: str

    # Entidades que el usuario menciono, ya resueltas a su id real en Neo4j.
    # Ej: [{"texto": "sistemas", "label": "Carrera", "id": "CAR_...", "nombre": "INGENIERIA..."}]
    entidades: list[dict]

    # La consulta Cypher generada por el LLM. La llena genera_cypher.
    cypher: str

    # Las filas que devolvio Neo4j al ejecutar el Cypher. Las llena ejecuta_cypher.
    filas: list[dict]

    # La respuesta final en espanol para el usuario. La llena analiza_resultado.
    respuesta: str

    # Cuantos intentos de generar Cypher llevamos (para el reintento con auto-correccion).
    intentos: int

    # Mensaje de error si algo fallo (ej. Cypher invalido). None/ausente si todo va bien.
    error: str

    # Ultimos turnos de la conversacion (pregunta+respuesta), para resolver referencias
    # tipo "esa carrera". Persiste entre preguntas via el checkpointer (MemorySaver).
    historial: list[dict]
