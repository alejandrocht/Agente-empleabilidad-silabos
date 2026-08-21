"""Deterministic quality checks for public agent responses."""

from __future__ import annotations

import re

MIN_RESPONSE_LENGTH = 10
MAX_RESPONSE_LENGTH = 2_000

_WORD = re.compile(r"[a-záéíóúüñ]+", re.IGNORECASE)
_UNSUPPORTED_SCRIPT = re.compile(
    r"[\u0370-\u03ff\u0400-\u04ff\u0600-\u06ff\u3040-\u30ff"
    r"\u3400-\u9fff\uac00-\ud7af]"
)
_UNSUPPORTED_OUTPUT = re.compile(
    r"(?:"
    r"\bas an ai(?: language model)?\b|"
    r"\bcomo modelo de lenguaje\b|"
    r"\baccording to my knowledge\b|"
    r"\bsegún mis conocimientos\b|"
    r"\bi (?:searched|queried|checked|looked up)\b|"
    r"\b(?:consulté|consulte|he consultado)\s+(?:neo4j|la base|fuentes)\b|"
    r"\b(?:hice|realicé|realice)\s+una búsqueda externa\b|"
    r"\b(?:neo4j|cypher|langgraph|openai)\b|"
    r"\b(?:system prompt|system message|internal state|mensaje del sistema|prompt interno)\b|"
    r"\b(?:MATCH|OPTIONAL MATCH)\s*\(|"
    r"\bRETURN\s+[a-z_]"
    r")",
    re.IGNORECASE,
)
_SPANISH_MARKERS = frozenset(
    {
        "a",
        "actualmente",
        "carrera",
        "carreras",
        "como",
        "con",
        "consulta",
        "datos",
        "de",
        "del",
        "disponible",
        "disponibles",
        "el",
        "en",
        "empresa",
        "empresas",
        "encontré",
        "encontraron",
        "es",
        "esta",
        "estas",
        "este",
        "estos",
        "gracias",
        "hay",
        "hola",
        "informacion",
        "información",
        "la",
        "las",
        "los",
        "necesita",
        "necesito",
        "no",
        "o",
        "oferta",
        "ofertas",
        "para",
        "por",
        "pude",
        "puede",
        "que",
        "qué",
        "registradas",
        "respuesta",
        "resultados",
        "se",
        "son",
        "sobre",
        "una",
        "un",
        "y",
    }
)
_ENGLISH_MARKERS = frozenset(
    {
        "according",
        "answer",
        "are",
        "available",
        "based",
        "cannot",
        "companies",
        "company",
        "could",
        "found",
        "from",
        "have",
        "has",
        "hello",
        "help",
        "in",
        "is",
        "jobs",
        "offer",
        "offers",
        "of",
        "please",
        "results",
        "that",
        "the",
        "there",
        "this",
        "to",
        "were",
        "with",
        "would",
        "you",
        "your",
    }
)


def _looks_non_spanish(text: str) -> bool:
    words = set(_WORD.findall(text.lower()))
    spanish_hits = len(words & _SPANISH_MARKERS)
    english_hits = len(words & _ENGLISH_MARKERS)
    return english_hits >= 2 and english_hits > spanish_hits


def inspect_response(response: object) -> tuple[bool, str]:
    """Return whether a response is suitable for the public Spanish API."""
    if not isinstance(response, str) or len(response.strip()) < MIN_RESPONSE_LENGTH:
        return False, "response is empty or too short"
    if len(response) > MAX_RESPONSE_LENGTH:
        return False, "response is too long"
    if _UNSUPPORTED_SCRIPT.search(response):
        return False, "response contains an unsupported script"
    if _looks_non_spanish(response):
        return False, "response does not appear to be Spanish"
    if _UNSUPPORTED_OUTPUT.search(response):
        return False, "response contains an unsupported or hallucinated signal"
    return True, ""
