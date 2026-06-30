"""
Nodo 1: obtiene_pregunta

Es el primer nodo del grafo. Su trabajo es sencillo: tomar la pregunta que el usuario
escribio (que ya viene en el estado inicial) y dejarla limpia para los siguientes nodos.
"""
from __future__ import annotations

from estado import EstadoAgente
from nodos.nodo import Nodo

# Saludos y cortesias que NO son preguntas de grafo: respondemos sin tocar Neo4j.
SALUDOS = {
    "hola", "buenas", "hey", "ola", "saludos", "que tal", "qué tal",
    "buenos dias", "buenos días", "buenas tardes", "buenas noches",
    "hi", "hello", "gracias", "ok", "adios", "adiós", "chau",
}

# Mensaje de ayuda que damos ante un saludo o entrada sin sentido de grafo.
AYUDA = (
    "Soy el agente del CIAR. Hazme preguntas sobre el grafo (carreras, cursos, "
    "evaluaciones, etc.). Ejemplos: \"¿Cuántas carreras hay?\" o "
    "\"¿Qué cursos tiene Ingeniería de Sistemas?\"."
)


class ObtienePregunta(Nodo):
    """Toma y limpia la pregunta del usuario; filtra saludos y resetea el turno."""

    # Nombre del nodo (se usa al registrarlo en el grafo).
    nombre = "obtiene_pregunta"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Leemos la pregunta del estado; si no hay, usamos texto vacio para no romper.
        pregunta = estado.get("pregunta", "")
        # Le quitamos espacios sobrantes al inicio y al final.
        pregunta_limpia = pregunta.strip()
        # IMPORTANTE: como el grafo recuerda el estado entre preguntas (MemorySaver),
        # reiniciamos el contador de intentos y el error en CADA pregunta nueva.
        # Si no, el contador se acumularia y el reintento dejaria de funcionar.
        return {"pregunta": pregunta_limpia, "intentos": 0, "error": None}
