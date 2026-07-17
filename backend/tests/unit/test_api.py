"""Contrato público de la API y sanitización de errores externos."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from agente.api import servidor


class GrafoFalso:
    """Emite un turno mínimo o la excepción configurada."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def stream(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        yield {"obtiene_pregunta": {"pregunta": "hola"}}
        yield {"devuelve_resultado": {"respuesta": "Respuesta segura y completa."}}


def test_chat_devuelve_ruta_y_respuesta(monkeypatch) -> None:
    monkeypatch.setattr(servidor, "grafo", GrafoFalso())

    salida = servidor.chat(servidor.ChatIn(pregunta="hola", id_sesion="sesion-segura"))

    assert salida["respuesta"] == "Respuesta segura y completa."
    assert salida["pasos"] == ["obtiene_pregunta", "devuelve_resultado"]


def test_chat_oculta_error_de_cuota(monkeypatch) -> None:
    rate_limit_error = type("RateLimitError", (Exception,), {})
    monkeypatch.setattr(servidor, "grafo", GrafoFalso(rate_limit_error("detalle secreto")))

    with pytest.raises(HTTPException) as capturada:
        servidor.chat(servidor.ChatIn(pregunta="consulta", id_sesion="sesion-segura"))

    assert capturada.value.status_code == 503
    assert "detalle secreto" not in capturada.value.detail
    assert "cuota" in capturada.value.detail


def test_dashboard_expone_carreras_y_error_de_filtros(monkeypatch) -> None:
    monkeypatch.setattr(
        servidor.dashboard,
        "listar_carreras",
        lambda: [{"id": "CAR_1", "nombre": "Sistemas", "cobertura_disponible": True}],
    )

    salida = servidor.dashboard_carreras()

    assert salida["carreras"][0]["id"] == "CAR_1"

    def demanda_invalida(*_args, **_kwargs):
        raise servidor.dashboard.ErrorDashboard("Dimensión no válida.")

    monkeypatch.setattr(servidor.dashboard, "demanda_dimension", demanda_invalida)
    with pytest.raises(HTTPException) as capturada:
        servidor.dashboard_demanda(
            "invalida",
            "CAR_1",
            date(2025, 1, 1),
            date(2025, 1, 31),
        )

    assert capturada.value.status_code == 400
    assert capturada.value.detail == "Dimensión no válida."
