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
        # Normalizamos para comparar: minusculas y sin signos al inicio/fin.
        normal = pregunta_limpia.lower().strip("¿?¡!.,")
        # MemorySaver persiste el estado entre preguntas: reseteamos TODO lo del turno
        # anterior (cypher, entidades, filas, intentos) menos "historial", que es lo
        # unico que debe sobrevivir entre preguntas.
        reset_turno = {"cypher": "", "entidades": [], "filas": [], "intentos": 0}

        # Si es saludo o entrada muy corta: respondemos con ayuda y NO vamos a Neo4j.
        if normal in SALUDOS or len(normal) < 3:
            return {"pregunta": pregunta_limpia, "respuesta": AYUDA, "error": None, **reset_turno}
        # Pregunta normal: sigue el pipeline completo.
        return {"pregunta": pregunta_limpia, "respuesta": "", "error": None, **reset_turno}
