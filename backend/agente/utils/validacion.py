import re

from agente.utils.logger import log_event

MAX_PREGUNTA_CHARS = 500

# Prompt injection — instrucciones que intentan sobreescribir el comportamiento del LLM
_PROMPT_INJECTION = [
    # Inglés
    r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"(?i)forget\s+(everything|all|previous|prior)",
    r"(?i)(you\s+are\s+now|act\s+as|pretend\s+(to\s+be|you\s+are))",
    r"(?i)(new\s+instructions?|your\s+(new\s+)?role\s+is)",
    r"(?i)(jailbreak|dan\s+mode|developer\s+mode|god\s+mode)",
    r"(?i)(<\s*system\s*>|\[system\]|###\s*system|---\s*system)",
    r"(?i)(disregard|override)\s+(your\s+)?(previous\s+)?(instructions?|training|rules?)",
    # Español
    r"(?i)ignora\s+(todas?\s+las?\s+)?(instrucciones?|reglas?|anteriores?)",
    r"(?i)(olvida|descarta)\s+(todo|lo\s+anterior|tus\s+instrucciones?)",
    r"(?i)(ahora\s+eres?|actúa\s+como|actua\s+como|pretende\s+ser|simula\s+ser)",
    r"(?i)(nuevas?\s+instrucciones?|tu\s+(nuevo\s+)?rol\s+es)",
    r"(?i)(modo\s+desarrollador|modo\s+dios|sin\s+restricciones?)",
    # Caracteres de control y zero-width
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
    r"[​‌‍‪-‮⁠﻿]",
]

# Cypher injection — sintaxis que no debería aparecer en lenguaje natural
_CYPHER_INJECTION = [
    # A public question must be natural language, never an arbitrary Cypher
    # statement. Reject clause-led input before it can reach the LLM or graph.
    (
        r"(?is)^\s*(?:(?:EXPLAIN|PROFILE)\s+)?"
        r"(?:OPTIONAL\s+MATCH|MATCH|CREATE|MERGE|DELETE|DETACH|DROP|REMOVE|SET|CALL|"
        r"LOAD|UNWIND|SHOW|TERMINATE|RETURN|WITH|USE)\b"
    ),
    r"(?i)\b(CREATE|MERGE|DELETE|DETACH\s+DELETE|DROP|REMOVE)\b\s*[\(\`]",
    r"(?i)\bDETACH\s+DELETE\b",
    r"(?i)\bLOAD\s+CSV\b",
    r"(?i)\bCALL\s+(dbms|apoc|db)\.",
    r"(?i)\bFOREACH\s*\(",
    r"(?i)\bSET\s+\w+[\.\[]?\w*\s*[+\-]?=",
    r"/\*[\s\S]*?\*/",
    r"(?i);\s*(MATCH|CREATE|MERGE|DELETE|SET|DROP|REMOVE|CALL|LOAD)",
    r"`[^`]{1,100}`\s*[\:\(]",
]


class EntradaInvalida(ValueError):
    def __init__(self, tipo: str, mensaje: str):
        self.tipo = tipo
        super().__init__(mensaje)


def validar_pregunta(texto: object) -> str:
    """Validate public question input before any model or database work."""
    if not isinstance(texto, str):
        log_event("input_validation", "rejected", reason="invalid_input")
        raise EntradaInvalida("invalid_input", "La pregunta debe ser texto.")
    if not texto.strip():
        log_event("input_validation", "rejected", reason="empty_input", length=0)
        raise EntradaInvalida("empty_input", "La pregunta no puede estar vacía")
    if len(texto) > MAX_PREGUNTA_CHARS:
        log_event(
            "input_validation",
            "rejected",
            reason="input_too_long",
            length=len(texto),
        )
        raise EntradaInvalida(
            "input_too_long",
            f"La pregunta no puede superar los {MAX_PREGUNTA_CHARS} caracteres.",
        )
    for patron in _PROMPT_INJECTION:
        if re.search(patron, texto):
            log_event("input_validation", "rejected", reason="prompt_injection", length=len(texto))
            raise EntradaInvalida(
                "prompt_injection",
                "Entrada rechazada: intento de manipulación detectado.",
            )

    for patron in _CYPHER_INJECTION:
        if re.search(patron, texto):
            log_event("input_validation", "rejected", reason="cypher_injection", length=len(texto))
            raise EntradaInvalida(
                "cypher_injection",
                "Entrada rechazada: sintaxis de consulta no permitida.",
            )
    return texto
