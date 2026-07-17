"""Auditoría de los eventos y su presentación en terminal."""

from __future__ import annotations

import json
import logging

from agente.observabilidad.logger import FormateadorLegible, log_paso


def test_log_paso_emite_json_con_claves(caplog) -> None:
    caplog.set_level(logging.INFO, logger="agente")
    log_paso("prueba", "inicio", "sesion-1", {"cantidad": 2})

    entrada = json.loads(caplog.records[-1].message)
    assert entrada["nodo"] == "prueba"
    assert entrada["evento"] == "inicio"
    assert entrada["sesion"] == "sesion-1"
    assert entrada["data"] == {"cantidad": 2}
    assert entrada["ts"]


def test_formateador_legible_muestra_evento_y_datos() -> None:
    entrada = {
        "ts": "2026-07-17T15:20:30.123456+00:00",
        "sesion": "sesion-1",
        "nodo": "prueba",
        "evento": "inicio",
        "data": {"cantidad": 2},
    }
    record = logging.LogRecord(
        "agente", logging.INFO, __file__, 1, json.dumps(entrada), (), None
    )

    salida = FormateadorLegible().format(record)

    assert salida == "15:20:30.123 | INFO    | sesion-1 | prueba.inicio | cantidad=2"


def test_formateador_legible_muestra_funcion_y_duracion() -> None:
    entrada = {
        "ts": "2026-07-17T15:20:30+00:00",
        "sesion": "sesion-1",
        "nodo": "funcion",
        "evento": "salida",
        "data": {
            "nombre": "agente.guardas.entrada.validar_entrada",
            "profundidad": 1,
            "duracion_ms": 1.234,
        },
    }
    record = logging.LogRecord(
        "agente", logging.INFO, __file__, 1, json.dumps(entrada), (), None
    )

    salida = FormateadorLegible().format(record)

    assert "<< agente.guardas.entrada.validar_entrada() [1.23 ms]" in salida
