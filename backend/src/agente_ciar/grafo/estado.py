"""Estado explícito y tipado que LangGraph transporta entre los nodos."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Estrategia = Literal["cache", "plantilla", "dinamica"]


class EstadoAgente(TypedDict, total=False):
    """Campos mínimos del turno; todos son opcionales para admitir actualizaciones parciales."""

    pregunta: str
    id_sesion: str
    memoria_texto: str
    entidades_contexto: list[dict[str, Any]]
    schema_texto: str | None
    entidades: list[dict[str, Any]]
    cypher: str | None
    filas: list[dict[str, Any]]
    respuesta: str | None
    intentos: int
    error: str | None
    estrategia: Estrategia | None
    plantilla_id: str | None
