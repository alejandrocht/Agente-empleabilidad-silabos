"""Regression coverage for the post-HITL technical syllabus workflow."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from agente.api import neo4j_importacion, normalizador, servidor
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.modelos import EstadoEjecucion, ResultadoLimpiezaSilabos

ARCHIVOS_TECNICOS = (
    "salidas/curso.csv",
    "salidas/silabo.csv",
    "salidas/catalogo_competencias.csv",
    "salidas/catalogo_logros.csv",
    "salidas/cobertura_curricular.csv",
)


def _preparar_ejecucion(
    tmp_path: Path, *, estado: str = "no_publicado"
) -> tuple[GestorEjecuciones, str, Path]:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "entrada.zip",
        {"carrera": "SISTEMAS", "periodo": "2026-2"},
    )
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        json.dumps(
            {
                "id_propuesta": "PROP_TEC_1",
                "id_silabo": "SIL_1",
                "nombre_competencia": "Arquitectura de APIs",
                "descripcion": "Diseña APIs mantenibles.",
                "codigo_competencia": "T1",
                "catalogo_ref": "APIS",
                "logros": ["Diseña servicios mantenibles."],
                "evidencia": [{"fragmento": "Diseña servicios mantenibles."}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (reportes / "analisis_tecnico.json").write_text('{"estado":"COMPLETADO"}', encoding="utf-8")
    (reportes / "release_gate.json").write_text(
        json.dumps(
            {
                "version": "curricular-release-gate/v1",
                "decision": "BLOCK_IMPORT",
                "blockers": ["PENDING_TECHNICAL_APPROVAL"],
            }
        ),
        encoding="utf-8",
    )
    (directorio / "limpios").mkdir(parents=True, exist_ok=True)
    (directorio / "limpios" / "silabos.jsonl").write_text(
        json.dumps(
            {
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "carrera": "SISTEMAS",
                "periodo": "2026-2",
                "datos": {
                    "nombre_curso": "Servicios de software",
                    "codigo_curso": "SIS501",
                    "competencias_declaradas": [
                        {
                            "nombre": "Pensamiento crítico",
                            "descripcion": "Evalúa evidencia para decidir.",
                            "codigo": "G1",
                            "tipo": "generica",
                        }
                    ],
                    "logro_general": "Diseña servicios mantenibles.",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = cast(EstadoEjecucion, estado)
    ejecucion.configuracion_curricular = {"modo_analista": "technical"}
    ejecucion.limpieza_silabos = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=tuple(
            {
                "tipo": "csv_curricular",
                "archivo": archivo,
                "registros": 999,
                "bytes": 1,
                "sha256": "stale-metadata",
            }
            for archivo in reversed(ARCHIVOS_TECNICOS)
        ),
        hallazgos=(),
        release_gate={"decision": "BLOCK_IMPORT"},
    )
    gestor._persistir(ejecucion)
    return gestor, id_ejecucion, directorio


def _assert_metadata_matches_csv(directorio: Path, output: dict[str, object]) -> None:
    ruta = directorio / str(output["archivo"])
    assert output["bytes"] == ruta.stat().st_size
    assert output["sha256"] == hashlib.sha256(ruta.read_bytes()).hexdigest()
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        assert output["registros"] == sum(1 for _ in csv.DictReader(archivo))


def test_final_technical_add_reconciles_manifest_active_api_and_csv_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")
    revision = pendientes.json()["revision"]
    decision = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [{"id_pendiente": "PROP_TEC_1", "decision": "ADD"}],
            "actor": "qa",
            "revision": revision,
        },
    )

    assert decision.status_code == 200
    assert decision.json()["estado"] in {"limpiado", "limpiado_con_advertencias"}
    assert decision.json()["aprobacion"]["release_gate"]["decision"] == "ALLOW_IMPORT"

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}")
    assert estado.status_code == 200
    payload = estado.json()
    assert payload["estado"] in {"limpiado", "limpiado_con_advertencias"}
    assert payload["release_gate"]["decision"] == "ALLOW_IMPORT"
    assert payload["aprobacion_curricular"]["release_gate"]["decision"] == "ALLOW_IMPORT"
    outputs = payload["outputs"]
    assert [output["archivo"] for output in outputs] == list(ARCHIVOS_TECNICOS)
    assert payload["aprobacion_curricular"]["materializacion"]["outputs"] == outputs
    for output in outputs:
        _assert_metadata_matches_csv(directorio, output)
        descarga = cliente.get(
            f"/normalizador/ejecuciones/{id_ejecucion}/outputs/{output['archivo']}"
        )
        assert descarga.status_code == 200
        assert descarga.content

    class ImportadorFalso:
        def previsualizar(self, id_recibido: str) -> dict[str, object]:
            assert id_recibido == id_ejecucion
            return {"id_ejecucion": id_recibido, "puede_importar": True}

    monkeypatch.setattr(neo4j_importacion, "importador_neo4j", ImportadorFalso())
    validacion = cliente.post(
        "/neo4j/validar",
        json={"id_ejecucion": id_ejecucion},
    )
    assert validacion.status_code == 200
    assert validacion.json()["puede_importar"] is True

    manifest = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["estado"] == payload["estado"]
    assert manifest["outputs"] == outputs


def test_pending_technical_gate_remains_blocked_and_exposes_no_csvs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    pending = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")
    response = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [
                {
                    "id_pendiente": "PROP_TEC_1",
                    "decision": "KEEP_PENDING",
                }
            ],
            "revision": pending.json()["revision"],
        },
    )

    assert response.status_code == 200
    assert response.json()["aprobacion"]["release_gate"]["decision"] == "BLOCK_IMPORT"
    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()
    assert estado["release_gate"]["decision"] == "BLOCK_IMPORT"
    assert estado["outputs"] == []
    descarga = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/{ARCHIVOS_TECNICOS[0]}"
    )
    assert descarga.status_code == 404
