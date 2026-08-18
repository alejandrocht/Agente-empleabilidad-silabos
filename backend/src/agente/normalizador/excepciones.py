"""Excepciones de control del ciclo de vida del normalizador."""

from __future__ import annotations


class CancelacionSolicitada(Exception):
    """Señala una cancelación cooperativa antes del siguiente lote costoso."""

    def __init__(self, mensaje: str = "La ejecución fue cancelada por el usuario.") -> None:
        super().__init__(mensaje)
