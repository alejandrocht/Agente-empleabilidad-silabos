"""Guarda determinista para rechazar entradas abusivas antes de consultar Neo4j u OpenAI."""

from __future__ import annotations

import re
import unicodedata

# Los patrones cubren instrucciones típicas que intentan sustituir el rol del sistema.
_PATRONES = [
    r"ignora\s+(todas?\s+)?(tus\s+|las\s+)?instrucciones",
    r"olvida\s+(todo|las\s+instrucciones|el\s+contexto)",
    r"ahora\s+eres",
    r"nuevo\s+rol",
    r"system\s*prompt",
    r"revela\s+(tu\s+)?(prompt|instrucciones)",
    r"muestra\s+(tu\s+)?(prompt|clave|api\s*key)",
    r"jailbreak",
    r"act[uú]a\s+como",
    r"modo\s+desarrollador",
]
_REGEX = re.compile("|".join(_PATRONES), flags=re.IGNORECASE)
MAX_CHARS = 500


def _normalizar(texto: str) -> str:
    """Reduce acentos, separadores y espacios usados para ocultar patrones conocidos."""
    descompuesto = unicodedata.normalize("NFKD", texto.lower())
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sin_acentos).strip()


def validar_entrada(texto: str) -> tuple[bool, str]:
    """Devuelve si el texto es aceptable y un motivo breve cuando se rechaza."""
    if len(texto) > MAX_CHARS:
        return False, f"Pregunta demasiado larga ({len(texto)}/{MAX_CHARS})"
    if _REGEX.search(_normalizar(texto)):
        return False, "La pregunta contiene patrones no permitidos"
    return True, ""
