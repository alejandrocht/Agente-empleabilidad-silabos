"""Respuestas deterministas para mensajes conversacionales muy simples."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

RESPUESTA_SALUDO: Final[str] = (
    "Hola. Soy el agente CIAR. Puedo ayudarte con consultas académicas "
    "y de empleabilidad de la Universidad de Lima."
)
RESPUESTA_CAPACIDADES: Final[str] = (
    "Puedo ayudarte con carreras, cursos, empresas, ofertas laborales, "
    "habilidades y otras relaciones entre formación y empleo."
)

_SALUDOS: Final[frozenset[str]] = frozenset(
    {
        "buenas",
        "buenas tardes",
        "buenas noches",
        "buenos dias",
        "hola",
        "hey",
        "saludos",
    }
)
_PREGUNTAS_DE_CAPACIDADES: Final[frozenset[str]] = frozenset(
    {
        "que preguntas puedes resolver",
        "que puedes resolver",
        "que puedes hacer",
        "para que sirves",
    }
)


def _normalizar_mensaje(mensaje: str) -> str:
    sin_acentos = "".join(
        caracter
        for caracter in unicodedata.normalize("NFKD", mensaje.lower())
        if not unicodedata.combining(caracter)
    )
    return " ".join(re.findall(r"[a-z0-9]+", sin_acentos))


def respuesta_conversacional(pregunta: str) -> str | None:
    """Return a safe local answer for an exact greeting, if applicable."""
    normalized = _normalizar_mensaje(pregunta)
    if normalized in _SALUDOS:
        return RESPUESTA_SALUDO
    if normalized in _PREGUNTAS_DE_CAPACIDADES:
        return RESPUESTA_CAPACIDADES
    return None
