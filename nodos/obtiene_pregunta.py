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

        # IMPORTANTE: el grafo recuerda el estado entre preguntas (MemorySaver).
        # Reseteamos en CADA turno los campos que llenan los nodos de una consulta previa;
        # si no, la respuesta/cypher viejos se filtran y el enrutado los reusa (haciendo
        # que toda pregunta a partir de la 2da repita la respuesta anterior).
        # No tocamos 'historial' a proposito: es la memoria entre turnos que si queremos.
        cambios: dict = {
            "pregunta": pregunta_limpia,
            "intentos": 0,
            "error": None,
            "respuesta": None,
            "cypher": None,
        }

        # Si la entrada es un saludo/cortesia, respondemos con la ayuda y cortocircuitamos:
        # dejar 'respuesta' seteada hace que _ruta_tras_pregunta salte a devuelve_resultado.
        clave = pregunta_limpia.lower().strip("¿?¡!.")
        if clave in SALUDOS:
            cambios["respuesta"] = AYUDA

        return cambios
