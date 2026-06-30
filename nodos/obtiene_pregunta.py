"""
Nodo 1: obtiene_pregunta

Es el primer nodo del grafo. Su trabajo es sencillo: tomar la pregunta que el usuario
escribio (que ya viene en el estado inicial) y dejarla limpia para los siguientes nodos.
"""
from __future__ import annotations

from estado import EstadoAgente
from nodos.nodo import Nodo


class ObtienePregunta(Nodo):
    """Toma y limpia la pregunta del usuario."""

    # Nombre del nodo (se usa al registrarlo en el grafo).
    nombre = "obtiene_pregunta"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Leemos la pregunta del estado; si no hay, usamos texto vacio para no romper.
        pregunta = estado.get("pregunta", "")
        # Le quitamos espacios sobrantes al inicio y al final.
        pregunta_limpia = pregunta.strip()
        # Devolvemos solo la clave que modificamos: la pregunta ya limpia.
        return {"pregunta": pregunta_limpia}
