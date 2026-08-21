"""Final deterministic inspection before a response reaches public boundaries."""

from __future__ import annotations

from agente.grafo.estado import Estado
from agente.utils.logger import log_event
from agente.utils.response_inspector import inspect_response

SAFE_RESPONSE_INSPECTION_FALLBACK = "No pude generar una respuesta confiable para esta consulta."


def inspeccionar_respuesta(estado: Estado) -> Estado:
    """Replace unsuitable output without exposing inspection details in state."""
    response = estado.get("respuesta")
    valid, reason = inspect_response(response)
    if valid:
        log_event(
            "response_inspector",
            "accepted",
            length=len(response) if isinstance(response, str) else 0,
        )
        return {}

    log_event("response_inspector", "rejected", reason="invalid_response")
    existing_error = estado.get("error")
    return {
        "respuesta": SAFE_RESPONSE_INSPECTION_FALLBACK,
        "error": existing_error or "response_inspection_failed",
    }
