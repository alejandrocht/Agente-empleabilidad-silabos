"""Regression tests for technical CSV publication after HITL approval."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agente.api import normalizador, servidor
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.modelos import ResultadoLimpiezaSilabos
from agente.normalizador.silabos.contrato_salidas import ARCHIVOS_CURRICULARES_TECNICOS


def test_approved_technical_csvs_are_exposed_from_stale_active_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "silabos.zip",
        {"carrera": "SISTEMAS", "periodo": "2026-2"},
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "no_publicado"
    ejecucion.configuracion_curricular = {"modo_analista": "technical"}
    ejecucion.limpieza_silabos = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=(),
        hallazgos=(),
        release_gate={"decision": "BLOCK_IMPORT"},
    )
    for archivo in ARCHIVOS_CURRICULARES_TECNICOS:
        ruta = directorio / archivo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("id\nuno\n", encoding="utf-8")
    gate = {"decision": "ALLOW_IMPORT", "blockers": []}
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    (reportes / "release_gate.json").write_text(json.dumps(gate), encoding="utf-8")
    gestor._persistir(ejecucion)

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    respuesta = TestClient(servidor.app, client=("127.0.0.1", 0)).get(
        f"/normalizador/ejecuciones/{id_ejecucion}"
    )

    assert respuesta.status_code == 200
    outputs = respuesta.json()["outputs"]
    assert {output["archivo"] for output in outputs} == ARCHIVOS_CURRICULARES_TECNICOS
    assert all(output["bytes"] > 0 and output["sha256"] for output in outputs)
