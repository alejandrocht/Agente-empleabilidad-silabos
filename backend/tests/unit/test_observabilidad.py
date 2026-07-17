"""Auditoría del esquema estructurado, su formato humano y el saneamiento central."""

from __future__ import annotations

import json
import logging

from agente.observabilidad.logger import FormateadorLegible, log_paso


def test_log_paso_emite_evento_con_funcion_y_sesion_pseudonimizada(caplog) -> None:
    caplog.set_level(logging.INFO, logger="agente")
    log_paso("prueba", "inicio", "sesion-1", {"cantidad": 2})

    entrada = json.loads(caplog.records[-1].message)
    assert entrada["nodo"] == "prueba"
    assert entrada["evento"] == "prueba.inicio"
    assert entrada["accion"] == "inicio"
    assert entrada["sesion"].startswith("ses-")
    assert entrada["sesion"] != "sesion-1"
    assert entrada["funcion"].endswith(
        "test_log_paso_emite_evento_con_funcion_y_sesion_pseudonimizada"
    )
    assert entrada["data"] == {"cantidad": 2}
    assert entrada["ts"]


def test_formateador_legible_usa_campos_explicitos() -> None:
    entrada = {
        "ts": "2026-07-17T15:20:30.123456+00:00",
        "sesion": "ses-123",
        "evento": "memoria.contexto_cargado",
        "funcion": "agente.nodos.obtiene_pregunta.ObtienePregunta.__call__",
        "data": {"entidades_activas": 2},
    }
    record = logging.LogRecord(
        "agente", logging.INFO, __file__, 1, json.dumps(entrada), (), None
    )

    salida = FormateadorLegible().format(record)

    assert salida == (
        "15:20:30.123 [nivel]: INFO [sesion]: ses-123 "
        "[evento]: memoria.contexto_cargado "
        "[funcion]: agente.nodos.obtiene_pregunta.ObtienePregunta.__call__ "
        "[entidades_activas]: 2"
    )


def test_formateador_legible_muestra_duracion_de_funcion() -> None:
    entrada = {
        "ts": "2026-07-17T15:20:30+00:00",
        "sesion": "ses-123",
        "evento": "funcion.finalizada",
        "funcion": "agente.guardas.entrada.validar_entrada",
        "data": {"duracion_ms": 1.234},
    }
    record = logging.LogRecord(
        "agente", logging.DEBUG, __file__, 1, json.dumps(entrada), (), None
    )

    salida = FormateadorLegible().format(record)

    assert "[funcion]: agente.guardas.entrada.validar_entrada" in salida
    assert "[duracion_ms]: 1.234" in salida


def test_log_paso_redacta_secretos_y_evitar_inyeccion_de_lineas(caplog) -> None:
    caplog.set_level(logging.INFO, logger="agente")
    log_paso(
        "seguridad",
        "prueba",
        "sesion-1",
        {"api_key": "secreto", "texto": "primera\nsegunda"},
    )

    data = json.loads(caplog.records[-1].message)["data"]
    assert data["api_key"] == "[REDACTADO]"
    assert data["texto"] == "primera\\nsegunda"
