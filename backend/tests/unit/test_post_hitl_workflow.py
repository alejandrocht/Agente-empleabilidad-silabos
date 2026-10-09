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
from agente.normalizador.silabos import aprobaciones_tecnicas

ARCHIVOS_TECNICOS = (
    "salidas/curso.csv",
    "salidas/silabo.csv",
    "salidas/catalogo_competencias.csv",
    "salidas/catalogo_habilidades.csv",
    "salidas/catalogo_logros.csv",
    "salidas/cobertura_curricular.csv",
)


@pytest.fixture(autouse=True)
def catalogo_hab_tec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from openpyxl import Workbook

    from agente.normalizador.catalogo_hab_tec import GestorCatalogosHabTec

    base = tmp_path / "hab_tec"
    monkeypatch.setenv("NORMALIZADOR_HAB_TEC_DIR", str(base))
    fuente = tmp_path / "hab_tec.xlsx"
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None
    hoja.append(["Carrera", "id", "nombre", "descripcion"])
    hoja.append(["SISTEMAS", "HAB_TEC_0001", "Arquitectura de APIs", "Diseña APIs mantenibles."])
    hoja.append(
        [
            "INGENIERIA_DE_SISTEMAS",
            "HAB_TEC_0001",
            "Arquitectura de APIs",
            "Diseña APIs mantenibles.",
        ]
    )
    libro.save(fuente)
    gestor = GestorCatalogosHabTec(base, publicar_en_neo4j=lambda *_args: {})
    estado = gestor.crear_desde_archivo(fuente.name, fuente)
    catalogo = gestor._obtener(str(estado["id_catalogo"]))
    catalogo.modelo_embedding = "fixture-model"
    monkeypatch.setattr(gestor, "_embeddings", lambda *_args: [[1.0, 0.0], [1.0, 0.0]])
    gestor._vectorizar(catalogo)


def _preparar_ejecucion(
    tmp_path: Path, *, estado: str = "no_publicado", hitl: str | None = None
) -> tuple[GestorEjecuciones, str, Path]:
    gestor = GestorEjecuciones(tmp_path)
    parametros = {"carrera": "SISTEMAS", "periodo": "2026-2"}
    if hitl is not None:
        parametros["hitl"] = hitl
    id_ejecucion, directorio = gestor.crear("silabos", "entrada.zip", parametros)
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        json.dumps(
            {
                "id_propuesta": "PROP_TEC_1",
                "id_silabo": "SIL_1",
                "nombre_competencia": "Arquitectura de APIs",
                "descripcion_breve_competencia": "Diseña APIs mantenibles.",
                "codigo_competencia": "T1",
                "catalogo_ref": "HAB_TEC_0001",
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


def test_hitl_zero_auto_adds_pending_technical_proposals_at_terminal_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path, hitl="0")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    gestor._finalizar(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}")

    assert estado.status_code == 200
    assert estado.json()["release_gate"]["decision"] == "ALLOW_IMPORT"
    journal = (directorio / "salidas" / "reportes" / "decisiones_tecnicas.jsonl").read_text(
        encoding="utf-8"
    )
    decision = json.loads(journal)
    assert decision["id_propuesta"] == "PROP_TEC_1"
    assert decision["decision"] == "ADD"
    assert decision["actor"] == "automatico_hitl_0"


def test_hitl_zero_rechaza_habilidad_sin_referencia(
    tmp_path: Path,
) -> None:
    gestor, _, directorio = _preparar_ejecucion(tmp_path, hitl="0")
    ruta = directorio / "salidas" / "reportes" / "propuestas_tecnicas.jsonl"
    propuesta = json.loads(ruta.read_text(encoding="utf-8"))
    propuesta.pop("catalogo_ref")
    ruta.write_text(json.dumps(propuesta) + "\n", encoding="utf-8")
    ejecucion = gestor._obtener_objeto(directorio.name)
    gestor._finalizar(ejecucion)
    assert ejecucion.limpieza_silabos is not None
    assert ejecucion.limpieza_silabos.release_gate["decision"] == "BLOCK_IMPORT"
    assert any(h.codigo == "AUTO_APROBACION_TECNICA_FALLIDA" for h in ejecucion.hallazgos)
    assert not (ruta.parent / "decisiones_tecnicas.jsonl").exists()
    assert not (directorio / "salidas" / "catalogo_habilidades.csv").exists()


def test_hitl_one_keeps_pending_technical_proposals_for_manual_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path, hitl="1")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    gestor._finalizar(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()
    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes").json()

    assert estado["release_gate"]["decision"] == "BLOCK_IMPORT"
    assert pendientes["filas"][0]["decision"] is None
    assert not (directorio / "salidas" / "reportes" / "decisiones_tecnicas.jsonl").exists()


def test_hitl_zero_auto_add_drops_stale_derived_release_gate_blocker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path, hitl="0")
    (directorio / "salidas" / "reportes" / "release_gate.json").write_text(
        json.dumps(
            {
                "version": "curricular-release-gate/v1",
                "decision": "BLOCK_IMPORT",
                "blockers": [
                    "PENDING_TECHNICAL_APPROVAL",
                    "UNLINKED_SOURCE_OUTCOME",
                ],
            }
        ),
        encoding="utf-8",
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    gestor._finalizar(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()

    assert estado["release_gate"]["decision"] == "ALLOW_IMPORT"
    assert "UNLINKED_SOURCE_OUTCOME" not in estado["release_gate"]["blockers"]


def test_hitl_zero_auto_add_preserves_unrelated_release_gate_blockers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path, hitl="0")
    gate = {
        "version": "curricular-release-gate/v1",
        "decision": "BLOCK_IMPORT",
        "blockers": [
            "PENDING_TECHNICAL_APPROVAL",
            "EXTRACTION_COVERAGE_INCOMPLETE",
            "STRUCTURAL_VALIDATION_FAILED",
        ],
        "checks": {
            "source_extraction": {"ok": False},
            "structural_validation": {"ok": False, "error": "invalid shape"},
        },
    }
    (directorio / "salidas" / "reportes" / "release_gate.json").write_text(
        json.dumps(gate), encoding="utf-8"
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    gestor._finalizar(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    estado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()

    assert estado["release_gate"]["decision"] == "BLOCK_IMPORT"
    assert {
        "EXTRACTION_COVERAGE_INCOMPLETE",
        "STRUCTURAL_VALIDATION_FAILED",
    } <= set(estado["release_gate"]["blockers"])
    assert estado["release_gate"]["checks"]["source_extraction"]["ok"] is False
    assert estado["release_gate"]["checks"]["structural_validation"]["ok"] is False
    assert estado["outputs"] == []
    descarga = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/outputs/{ARCHIVOS_TECNICOS[0]}"
    )
    assert descarga.status_code == 200
    assert descarga.content


def test_manifest_allow_does_not_promote_state_when_public_gate_blocks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    manifest_path = directorio / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["estado"] = "limpiado"
    manifest["release_gate"] = {"decision": "ALLOW_IMPORT"}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    payload = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}").json()

    assert payload["estado"] == "no_publicado"
    assert payload["release_gate"]["decision"] == "BLOCK_IMPORT"
    assert payload["outputs"] == []


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
    assert gestor._obtener_objeto(id_ejecucion).estado == "no_publicado"
    assert manifest["estado"] in {"limpiado", "limpiado_con_advertencias"}
    assert payload["estado"] == manifest["estado"]
    assert gestor.obtener(id_ejecucion)["estado"] == payload["estado"]
    assert manifest["outputs"] == outputs


def test_pending_technical_gate_blocks_import_but_keeps_csv_draft_downloadable(
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
    assert descarga.status_code == 200
    assert descarga.content


def test_final_technical_add_uses_canonical_manifest_validation_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    manifest_path = directorio / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["parametros"]["carrera"] = "Ingeniería de Sistemas"
    manifest["validacion_silabos"] = {
        "carrera": "INGENIERIA_DE_SISTEMAS",
        "periodo": "2026-2",
        "valida": True,
    }
    registros_path = directorio / "limpios" / "silabos.jsonl"
    registro = json.loads(registros_path.read_text(encoding="utf-8"))
    registro["carrera"] = "INGENIERIA_DE_SISTEMAS"
    registros_path.write_text(json.dumps(registro) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")
    response = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [{"id_pendiente": "PROP_TEC_1", "decision": "ADD"}],
            "revision": pendientes.json()["revision"],
        },
    )

    assert response.status_code == 200
    assert response.json()["aprobacion"]["release_gate"]["decision"] == "ALLOW_IMPORT"


def test_mixed_career_rejects_add_without_persisting_decision(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    manifest_path = directorio / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validacion_silabos"] = {
        "carrera": "SISTEMAS",
        "periodo": "2026-2",
        "valida": True,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registros_path = directorio / "limpios" / "silabos.jsonl"
    registros = [json.loads(linea) for linea in registros_path.read_text().splitlines()]
    registros.append(
        {
            **registros[0],
            "id_curso": "CUR_2",
            "id_silabo": "SIL_2",
            "carrera": "OTRA_CARRERA",
        }
    )
    registros_path.write_text(
        "".join(json.dumps(registro) + "\n" for registro in registros), encoding="utf-8"
    )
    gate_path = directorio / "salidas" / "reportes" / "release_gate.json"
    gate_before = gate_path.read_bytes()
    manifest_before = manifest_path.read_bytes()

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")
    response = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [{"id_pendiente": "PROP_TEC_1", "decision": "ADD"}],
            "revision": pendientes.json()["revision"],
        },
    )

    assert response.status_code == 422
    assert "mezcla carreras" in response.json()["detail"]
    assert not (directorio / "salidas" / "reportes" / "decisiones_tecnicas.jsonl").exists()
    assert gate_path.read_bytes() == gate_before
    assert manifest_path.read_bytes() == manifest_before


def test_pending_api_deduplicates_persisted_proposals_by_normalized_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    reportes = directorio / "salidas" / "reportes"
    propuestas = [
        {
            "id_propuesta": "PROP_TEC_1",
            "id_silabo": "SIL_1",
            "nombre_competencia": "Arquitectura de APIs",
            "descripcion_breve_competencia": "Diseña APIs mantenibles.",
            "catalogo_ref": "HAB_TEC_0001",
            "logros": ["Diseña servicios mantenibles."],
        },
        {
            "id_propuesta": "PROP_TEC_2",
            "id_silabo": "SIL_1",
            "nombre_competencia": " configurar   redes INFORMATICAS ",
            "descripcion": "Duplicate proposal must remain audit-only.",
            "catalogo_ref": "HAB_TEC_0001",
            "logros": ["Duplicate outcome"],
        },
        {
            "id_propuesta": "PROP_TEC_3",
            "id_silabo": "SIL_1",
            "nombre_competencia": "Monitorear redes informáticas",
            "descripcion": "Distinct name must remain visible.",
            "catalogo_ref": "HAB_TEC_0002",
            "logros": ["Diseña servicios mantenibles."],
        },
    ]
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        "".join(json.dumps(propuesta) + "\n" for propuesta in propuestas),
        encoding="utf-8",
    )

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    response = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")

    assert response.status_code == 200
    payload = response.json()
    assert [fila["id_pendiente"] for fila in payload["filas"]] == [
        "PROP_TEC_1",
        "PROP_TEC_3",
    ]
    assert payload["filas"][0]["descripcion_breve_competencia"] == "Diseña APIs mantenibles."
    assert payload["aprobacion"]["total"] == 2

    decision = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [
                {"id_pendiente": "PROP_TEC_1", "decision": "ADD"},
                {"id_pendiente": "PROP_TEC_3", "decision": "DISCARD"},
            ],
            "revision": payload["revision"],
        },
    )

    assert decision.status_code == 200
    assert decision.json()["aprobacion"]["release_gate"]["decision"] == "ALLOW_IMPORT"
    journal = (reportes / "decisiones_tecnicas.jsonl").read_text(encoding="utf-8")
    assert "PROP_TEC_2" not in journal
    assert "PROP_TEC_2" in (reportes / "propuestas_tecnicas.jsonl").read_text(encoding="utf-8")


def test_session_authored_pending_api_keeps_cross_syllabus_names_and_accepts_each_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    reportes = directorio / "salidas" / "reportes"
    (reportes / "analisis_tecnico.json").write_text(
        json.dumps({"estado": "COMPLETADO", "modo_ejecucion": "SESSION_AUTHORED"}),
        encoding="utf-8",
    )
    propuestas = [
        {
            "id_propuesta": "PROP_TEC_SIL_1",
            "id_silabo": "SIL_1",
            "nombre_competencia": "Evaluación psicológica",
            "descripcion": "First syllabus proposal.",
            "catalogo_ref": "COMP_TEC_0002",
            "logros": ["Evalúa evidencia clínica."],
        },
        {
            "id_propuesta": "PROP_TEC_SIL_2",
            "id_silabo": "SIL_2",
            "nombre_competencia": " evaluacion PSICOLOGICA ",
            "descripcion": "Same reusable skill for another syllabus.",
            "catalogo_ref": "COMP_TEC_0002",
            "logros": ["Evalúa evidencia clínica."],
        },
        {
            "id_propuesta": "PROP_TEC_SIL_1_DUP",
            "id_silabo": "SIL_1",
            "nombre_competencia": "EVALUACIÓN psicológica",
            "descripcion": "Same-syllabus duplicate stays audit-only.",
            "catalogo_ref": "COMP_TEC_0002",
        },
    ]
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        "".join(json.dumps(propuesta) + "\n" for propuesta in propuestas),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        aprobaciones_tecnicas,
        "_materializar",
        lambda *args, **kwargs: {
            "decision": "BLOCK_IMPORT",
            "blockers": ["UNLINKED_SOURCE_OUTCOME"],
        },
    )
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")

    assert pendientes.status_code == 200
    payload = pendientes.json()
    assert [fila["id_pendiente"] for fila in payload["filas"]] == [
        "PROP_TEC_SIL_1",
        "PROP_TEC_SIL_2",
    ]
    decision = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [
                {"id_pendiente": "PROP_TEC_SIL_1", "decision": "ADD"},
                {"id_pendiente": "PROP_TEC_SIL_2", "decision": "ADD"},
            ],
            "revision": payload["revision"],
        },
    )

    assert decision.status_code == 200
    journal = [
        json.loads(line)
        for line in (reportes / "decisiones_tecnicas.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [fila["id_propuesta"] for fila in journal] == [
        "PROP_TEC_SIL_1",
        "PROP_TEC_SIL_2",
    ]
    assert decision.json()["aprobacion"]["accepted"] == 2
    assert decision.json()["aprobacion"]["release_gate"]["decision"] == "BLOCK_IMPORT"


def test_pending_api_ignores_duplicate_journal_rows_but_rejects_true_orphans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    reportes = directorio / "salidas" / "reportes"
    propuestas = [
        {
            "id_propuesta": "PROP_TEC_1",
            "id_silabo": "SIL_1",
            "nombre_competencia": "Configurar redes informáticas.",
            "descripcion": "Retained proposal.",
        },
        {
            "id_propuesta": "PROP_TEC_2",
            "id_silabo": "SIL_1",
            "nombre_competencia": " configurar redes INFORMATICAS ",
            "descripcion": "Deduplicated proposal.",
        },
    ]
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        "".join(json.dumps(propuesta) + "\n" for propuesta in propuestas),
        encoding="utf-8",
    )
    journal_path = reportes / "decisiones_tecnicas.jsonl"
    journal_path.write_text(
        json.dumps({"id_propuesta": "PROP_TEC_2", "decision": "DISCARD"}) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    duplicate_journal_response = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")

    assert duplicate_journal_response.status_code == 200
    assert [fila["id_pendiente"] for fila in duplicate_journal_response.json()["filas"]] == [
        "PROP_TEC_1"
    ]
    assert duplicate_journal_response.json()["filas"][0]["decision"] is None

    journal_path.write_text(
        "".join(
            json.dumps(fila) + "\n"
            for fila in [
                {"id_propuesta": "PROP_TEC_2", "decision": "DISCARD"},
                {"id_propuesta": "PROP_TEC_ORPHAN", "decision": "DISCARD"},
            ]
        ),
        encoding="utf-8",
    )
    orphan_response = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")

    assert orphan_response.status_code == 422
    assert "PROP_TEC_ORPHAN" in orphan_response.json()["detail"]


def test_legacy_manifest_rechaza_habilidad_nueva(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    reportes = directorio / "salidas" / "reportes"
    (reportes / "propuestas_tecnicas.jsonl").write_text(
        json.dumps(
            {
                "id_propuesta": "PROP_TEC_SIN_CATALOGO",
                "id_silabo": "SIL_1",
                "nombre_competencia": "Machine Learning Avanzado",
                "descripcion": "Construye modelos predictivos escalables.",
                "codigo_competencia": "T_ML",
                "logros": ["Diseña servicios mantenibles."],
                "evidencia": [{"fragmento": "Diseña servicios mantenibles."}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = directorio / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "ruta_catalogo_tecnico" not in manifest["configuracion_curricular"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))
    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")
    assert pendientes.status_code == 200
    decision = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [{"id_pendiente": "PROP_TEC_SIN_CATALOGO", "decision": "ADD"}],
            "revision": pendientes.json()["revision"],
        },
    )

    assert decision.status_code == 422
    assert "referenciar el catálogo" in decision.json()["detail"]
    assert not (reportes / "decisiones_tecnicas.jsonl").exists()
    assert not (directorio / "salidas" / "catalogo_habilidades.csv").exists()


def test_habilidad_catalogada_revierte_publicacion_si_manifest_falla(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A failed manifest write rolls back closed-catalog CSV and journal publication."""
    import openpyxl

    gestor, id_ejecucion, directorio = _preparar_ejecucion(tmp_path)
    reportes = directorio / "salidas" / "reportes"

    (reportes / "propuestas_tecnicas.jsonl").write_text(
        json.dumps(
            {
                "id_propuesta": "PROP_TEC_NUEVA",
                "id_silabo": "SIL_1",
                "catalogo_ref": "HAB_TEC_0001",
                "nombre_competencia": "Arquitectura de APIs",
                "descripcion_breve_competencia": "Diseña APIs mantenibles.",
                "codigo_competencia": "T_ML",
                "logros": ["Diseña servicios mantenibles."],
                "evidencia": [{"fragmento": "Implementa pipelines ML."}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    csv_path = tmp_path / "carrera_competencia_oficial.csv"
    csv_path.write_text(
        "id_carrera,nombre_carrera,id_habilidad,nombre_habilidad\n"
        "CAR_SIS,Sistemas,COMP_TEC_0001,API Architecture\n",
        encoding="utf-8",
    )

    xlsx_path = tmp_path / "catalogo_competencias_tecnicas.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Carrera", "Habilidad tecnica", "Descripcion"])
    ws.append(["Sistemas", "API Architecture", "Diseña APIs mantenibles"])
    wb.save(xlsx_path)

    ejecucion = gestor._obtener_objeto(id_ejecucion)
    assert ejecucion.configuracion_curricular is not None
    ejecucion.configuracion_curricular["ruta_catalogo_tecnico"] = str(csv_path)
    gestor._persistir(ejecucion)

    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    pendientes = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/pendientes")
    assert pendientes.status_code == 200
    revision = pendientes.json()["revision"]
    manifest_path = directorio / "manifest.json"
    manifest_before = manifest_path.read_bytes()
    journal_path = reportes / "decisiones_tecnicas.jsonl"
    catalogo_habilidades_path = directorio / "salidas" / "catalogo_habilidades.csv"
    assert not journal_path.exists()
    assert not catalogo_habilidades_path.exists()

    persistir_manifest_original = aprobaciones_tecnicas._persistir_manifest

    def persistir_manifest_fallido(
        directorio_manifest: Path,
        manifest: dict[str, object],
        gate: dict[str, object],
        resumen: dict[str, object],
    ) -> None:
        persistir_manifest_original(directorio_manifest, manifest, gate, resumen)
        raise RuntimeError("simulated manifest failure")

    monkeypatch.setattr(
        aprobaciones_tecnicas,
        "_persistir_manifest",
        persistir_manifest_fallido,
    )
    with pytest.raises(RuntimeError, match="simulated manifest failure"):
        aprobaciones_tecnicas.aplicar_decisiones(
            directorio,
            [{"id_pendiente": "PROP_TEC_NUEVA", "decision": "ADD"}],
            revision=revision,
        )

    assert manifest_path.read_bytes() == manifest_before
    assert not journal_path.exists()
    assert not catalogo_habilidades_path.exists()
    registry_path = directorio.parent / "catalogos" / "habilidades.sqlite3"
    assert not registry_path.exists()
