"""Auditoría del formato JSON usado por todos los pasos."""

from __future__ import annotations

import json
import logging

from agente_ciar.observabilidad.logger import log_paso


def test_log_paso_emite_json_con_claves(caplog) -> None:
    caplog.set_level(logging.INFO, logger="agente_ciar")
    log_paso("prueba", "inicio", "sesion-1", {"cantidad": 2})

    entrada = json.loads(caplog.records[-1].message)
    assert entrada["nodo"] == "prueba"
    assert entrada["evento"] == "inicio"
    assert entrada["sesion"] == "sesion-1"
    assert entrada["data"] == {"cantidad": 2}
    assert entrada["ts"]
