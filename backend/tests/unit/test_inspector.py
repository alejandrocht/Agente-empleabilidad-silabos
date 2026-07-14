"""Auditoría del inspector determinista de respuestas."""

from __future__ import annotations

from agente_ciar.nodos.devuelve_resultado import _inspeccionar


def test_inspector_rechaza_respuestas_invalidas() -> None:
    assert _inspeccionar("")[0] is False
    assert _inspeccionar("muy corta")[0] is False
    assert _inspeccionar("x" * 3000)[0] is False
    assert _inspeccionar("Respuesta con 字 inesperado")[0] is False


def test_inspector_acepta_respuesta_normal() -> None:
    assert _inspeccionar("Hay catorce carreras registradas.") == (True, "")
