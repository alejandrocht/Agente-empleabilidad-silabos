"""Formatea el historial reciente de la conversacion para inyectarlo en prompts."""
from __future__ import annotations


def formatear_historial(historial: list[dict] | None) -> str:
    """Convierte la lista de turnos previos en texto legible para el LLM."""
    if not historial:
        return "(sin turnos previos)"
    bloques = [
        f"Pregunta: {turno.get('pregunta', '')}\nRespuesta: {turno.get('respuesta', '')}"
        for turno in historial
    ]
    return "\n\n".join(bloques)
