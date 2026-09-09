"""Public-interface tests for the curricular approval checkpoint."""

from __future__ import annotations

import ast
import csv
import inspect
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agente.api import normalizador, servidor
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.modelos import ArchivoSilabo, ResultadoValidacionSilabos
from agente.normalizador.silabos import analista_llm, aprobaciones, validacion_aprobaciones
from agente.normalizador.silabos.analista_llm import ConceptoPropuesto, DecisionCurricular
from agente.normalizador.silabos.salida import construir_salidas_curriculares


def _csv(ruta: Path, columnas: tuple[str, ...]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()


def _preparar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    gestor = GestorEjecuciones(tmp_path / "ejecuciones")
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "curriculo.zip",
        {"carrera": "Marketing", "periodo": "2026-1"},
    )
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "limpiado"
    gestor._persistir(ejecucion)

    salida = directorio / "salidas"
    reportes = salida / "reportes"
    reportes.mkdir(parents=True)
    _csv(salida / "catalogo_competencias.csv", aprobaciones.COMPETENCIAS_SCHEMA)
    _csv(salida / "catalogo_habilidades.csv", aprobaciones.HABILIDADES_SCHEMA)
    _csv(salida / "catalogo_herramientas.csv", aprobaciones.HERRAMIENTAS_SCHEMA)
    _csv(salida / "cobertura_curricular.csv", aprobaciones.COBERTURA_SCHEMA)
    (reportes / "pendientes_curriculares.jsonl").write_text(
        "\n".join(
            json.dumps(fila, ensure_ascii=False)
            for fila in (
                {
                    "id_pendiente": "PEN_COMP",
                    "tipo": "competencia",
                    "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_logro": "LOG_1",
                    "archivo": "curso.docx",
                    "id_habilidad_fuente": "HAB_SRC_1",
                    "descripcion_fuente": "Diseñar campañas.",
                    "propuesta": {
                        "nombre": "Diseño omnicanal",
                        "descripcion": "Diseñar campañas omnicanal.",
                        "tipo": "dura",
                    },
                    "evidencia": ["Diseñar campañas omnicanal."],
                },
                {
                    "id_pendiente": "PEN_TOOL",
                    "tipo": "herramienta",
                    "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
                    "id_curso": "CUR_1",
                    "id_silabo": "SIL_1",
                    "id_logro": "LOG_1",
                    "archivo": "curso.docx",
                    "id_habilidad_fuente": "HAB_SRC_1",
                    "descripcion_fuente": "Usar plataforma.",
                    "propuesta": {
                        "nombre": "CampaignOS",
                        "descripcion": "Plataforma curricular.",
                        "tipo": "herramienta",
                    },
                    "evidencia": ["Usar CampaignOS."],
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for nombre in (
        "competencias_fuente.jsonl",
        "habilidades_fuente.jsonl",
        "herramientas_fuente.jsonl",
        "cobertura_curricular_canonica.jsonl",
    ):
        (reportes / nombre).write_text("", encoding="utf-8")
    (reportes / "release_gate.json").write_text(
        json.dumps(
            {
                "version": "curricular-release-gate/v1",
                "decision": "BLOCK_IMPORT",
                "checks": {
                    "source_coverage": {"records": 1, "logros_fuente": 1},
                    "structural_errors": {"ok": True},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(aprobaciones, "ruta_catalogos", lambda: tmp_path / "catalogos")
    return directorio, id_ejecucion


def _arbol_de_bytes(*roots: Path) -> dict[Path, bytes]:
    return {
        ruta: ruta.read_bytes()
        for root in roots
        if root.is_dir()
        for ruta in root.rglob("*")
        if ruta.is_file() and not ruta.is_symlink()
    }


def test_validacion_reexporta_misma_identidad_y_no_importa_la_fachada() -> None:
    for nombre in (
        "DECISIONES_VALIDAS",
        "DecisionCurricularInvalida",
        "AprobacionNoPermitida",
        "RevisionCurricularInvalida",
        "_expandir_decisiones_de_paquete",
        "_validar_solicitudes",
        "_validar_precondiciones_promocion",
    ):
        fachada = getattr(aprobaciones, nombre)
        validacion = getattr(validacion_aprobaciones, nombre)
        assert fachada is validacion
        if inspect.isfunction(fachada):
            assert inspect.signature(fachada) == inspect.signature(validacion)
    imports = ast.walk(ast.parse(inspect.getsource(validacion_aprobaciones)))
    assert not any(
        isinstance(nodo, ast.ImportFrom)
        and nodo.module == "agente.normalizador.silabos.aprobaciones"
        for nodo in imports
    )


def test_error_tardio_restaura_el_arbol_de_bytes_de_aprobacion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    perfil = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    perfil.mkdir(parents=True)
    antes = _arbol_de_bytes(directorio, perfil)

    def fallar_manifest(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("fallo de manifest simulado")

    monkeypatch.setattr(aprobaciones, "_persistir_manifest_aprobacion", fallar_manifest)

    with pytest.raises(RuntimeError, match="fallo de manifest simulado"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [
                {"id_pendiente": "PEN_COMP", "decision": "ADD"},
                {"id_pendiente": "PEN_TOOL", "decision": "KEEP_PENDING"},
            ],
        )

    assert _arbol_de_bytes(directorio, perfil) == antes


def test_aprobar_y_mantener_pendiente_promueve_solo_al_perfil_y_conserva_evidencia(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_COMP", "decision": "ADD"},
            {"id_pendiente": "PEN_TOOL", "decision": "KEEP_PENDING"},
        ],
        actor="revisor@example.com",
    )

    assert resultado["aprobacion"]["accepted"] == 1
    assert resultado["aprobacion"]["remaining_pending"] == 1
    perfil = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    assert (perfil / "catalogo_competencias.csv").is_file()
    assert (
        list(csv.DictReader((perfil / "catalogo_herramientas.csv").open(encoding="utf-8-sig")))
        == []
    )
    pendientes = [
        json.loads(line)
        for line in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {fila["id_pendiente"]: fila["decision"] for fila in pendientes} == {
        "PEN_COMP": "ADD",
        "PEN_TOOL": "KEEP_PENDING",
    }
    assert pendientes[1]["evidencia"] == ["Usar CampaignOS."]
    decisiones = (
        (directorio / "salidas/reportes/decisiones_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert len(decisiones) == 2
    assert all("revisor@example.com" in linea for linea in decisiones)


def test_no_permite_promover_competencia_generica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    filas = [json.loads(line) for line in ruta.read_text(encoding="utf-8").splitlines()]
    filas[0]["propuesta"]["nombre"] = "Pensamiento crítico"
    ruta.write_text(
        "\n".join(json.dumps(fila, ensure_ascii=False) for fila in filas) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        aprobaciones.DecisionCurricularInvalida,
        match="COMPETENCIA_GENERICA",
    ):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [{"id_pendiente": "PEN_COMP", "decision": "ADD"}],
            actor="revisor@example.com",
        )


def test_release_gate_cuenta_una_vez_la_fila_sin_decision_y_conserva_keep_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    pendientes = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    pendientes.append(
        {
            "id_pendiente": "PEN_UNDECIDED",
            "tipo": "habilidad",
            "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_logro": "LOG_1",
            "archivo": "curso.docx",
            "id_habilidad_fuente": "HAB_SRC_2",
            "descripcion_fuente": "Analizar audiencias.",
            "propuesta": {"nombre": "Análisis de audiencias", "tipo": "blanda"},
            "evidencia": ["Analizar audiencias."],
        }
    )
    ruta.write_text(
        "".join(json.dumps(fila, ensure_ascii=False) + "\n" for fila in pendientes),
        encoding="utf-8",
    )

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_COMP", "decision": "ADD"},
            {"id_pendiente": "PEN_TOOL", "decision": "KEEP_PENDING"},
        ],
    )

    aprobacion = resultado["aprobacion"]["release_gate"]["approval"]
    assert aprobacion["pending_decision"] == 1
    assert aprobacion["unresolved_records"] == 1
    assert aprobacion["remaining_pending"] == 2


def test_summary_counts_raw_unresolved_rows_per_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)

    resumen = aprobaciones.resumen_aprobacion_curricular(directorio)

    assert resumen["por_tipo"]["competencia"] == {
        "total": 1,
        "requieren_decision": 1,
        "accepted": 0,
        "remaining_pending": 1,
    }
    assert resumen["por_tipo"]["herramienta"] == {
        "total": 1,
        "requieren_decision": 1,
        "accepted": 0,
        "remaining_pending": 1,
    }


def test_no_promueve_habilidad_sin_competencia_al_catalogo_ni_al_perfil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    ruta.write_text(
        json.dumps(
            {
                "id_pendiente": "PEN_SKILL_ONLY",
                "tipo": "habilidad",
                "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_logro": "LOG_1",
                "archivo": "curso.docx",
                "id_habilidad_fuente": "HAB_SRC_1",
                "descripcion_fuente": "Diseñar campañas.",
                "propuesta": {
                    "nombre": "Diseño de campañas",
                    "descripcion": "Diseñar campañas omnicanal.",
                },
                "evidencia": ["Diseñar campañas omnicanal."],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="habilidad"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [{"id_pendiente": "PEN_SKILL_ONLY", "decision": "ADD"}],
        )

    assert not list(
        csv.DictReader((directorio / "salidas/catalogo_habilidades.csv").open(encoding="utf-8-sig"))
    )
    perfil = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    assert not (perfil / "catalogo_habilidades.csv").exists()


def test_no_promueve_herramienta_sin_cadena_al_catalogo_ni_al_perfil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    ruta.write_text(
        json.dumps(
            {
                "id_pendiente": "PEN_TOOL_ONLY",
                "tipo": "herramienta",
                "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_logro": "LOG_1",
                "archivo": "curso.docx",
                "id_habilidad_fuente": "HAB_SRC_1",
                "descripcion_fuente": "Usar plataforma.",
                "propuesta": {
                    "nombre": "CampaignOS",
                    "descripcion": "Plataforma curricular.",
                    "tipo": "herramienta",
                },
                "evidencia": ["Usar CampaignOS."],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="herramienta"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [{"id_pendiente": "PEN_TOOL_ONLY", "decision": "ADD"}],
        )
    assert not list(
        csv.DictReader(
            (directorio / "salidas/catalogo_herramientas.csv").open(encoding="utf-8-sig")
        )
    )
    perfil = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    assert not (perfil / "catalogo_herramientas.csv").exists()


def test_decision_de_paquete_resuelve_todas_las_filas_accionables_de_forma_atomica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    paquete = aprobaciones._paquetes(directorio, aprobaciones._filas_clasificadas(directorio))[0]

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [{"id_paquete_chh": paquete["id_paquete_chh"], "decision": "KEEP_PENDING"}],
        actor="package-reviewer",
    )

    assert resultado["aprobacion"]["accepted_in_request"] == 0
    assert resultado["aprobacion"]["kept_pending_in_request"] == 2
    filas = [
        json.loads(line)
        for line in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {fila["decision"] for fila in filas} == {"KEEP_PENDING"}
    assert {fila["id_paquete_chh"] for fila in filas} == {paquete["id_paquete_chh"]}


def test_descartar_paquete_es_idempotente_y_conserva_auditoria(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    paquete = aprobaciones._paquetes(directorio, aprobaciones._filas_clasificadas(directorio))[0]
    solicitud = [
        {
            "id_paquete_chh": paquete["id_paquete_chh"],
            "decision": "DISCARD",
            "reason": "No corresponde al alcance curricular aprobado.",
        }
    ]

    primera = aprobaciones.aplicar_decisiones_curriculares(directorio, solicitud, actor="revisor")
    segunda = aprobaciones.aplicar_decisiones_curriculares(directorio, solicitud, actor="revisor")

    assert primera["aprobacion"]["discarded_in_request"] == 2
    assert segunda["aprobacion"]["discarded_in_request"] == 2
    assert aprobaciones.paquetes_para_revision(directorio) == []
    filas = aprobaciones._filas_clasificadas(directorio)
    assert {fila["decision"] for fila in filas} == {"DISCARD"}
    auditoria = [
        json.loads(linea)
        for linea in (directorio / "salidas/reportes/descartes_paquetes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(auditoria) == 1
    assert auditoria[0]["package_id"] == paquete["id_paquete_chh"]
    assert auditoria[0]["reason"] == "No corresponde al alcance curricular aprobado."


def test_repetir_la_misma_decision_es_idempotente_y_los_ids_duplicados_se_rechazan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    solicitud = [{"id_pendiente": "PEN_COMP", "decision": "ADD"}]

    primera = aprobaciones.aplicar_decisiones_curriculares(directorio, solicitud)
    segunda = aprobaciones.aplicar_decisiones_curriculares(directorio, solicitud)

    assert primera["aprobacion"] == segunda["aprobacion"]
    assert (
        len(
            (directorio / "salidas/reportes/decisiones_curriculares.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        == 1
    )
    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="duplicados"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [
                {"id_pendiente": "PEN_TOOL", "decision": "ADD"},
                {"id_pendiente": "PEN_TOOL", "decision": "KEEP_PENDING"},
            ],
        )


def test_aprobar_los_tres_extremos_materializa_una_cadena_chh_valida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    filas.append(
        {
            "id_pendiente": "PEN_SKILL",
            "tipo": "habilidad",
            "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_logro": "LOG_1",
            "archivo": "curso.docx",
            "id_habilidad_fuente": "HAB_SRC_1",
            "descripcion_fuente": "Analizar campañas.",
            "propuesta": {
                "nombre": "Analizar campañas",
                "descripcion": "Analizar campañas.",
            },
            "evidencia": ["Analizar campañas."],
        }
    )
    ruta.write_text("".join(json.dumps(fila) + "\n" for fila in filas), encoding="utf-8")

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_COMP", "decision": "ADD"},
            {"id_pendiente": "PEN_TOOL", "decision": "ADD"},
            {"id_pendiente": "PEN_SKILL", "decision": "ADD"},
        ],
    )

    gate = resultado["aprobacion"]["release_gate"]
    assert gate["decision"] == "ALLOW_IMPORT"
    assert gate["checks"]["chh_graph"]["ok"] is True
    cobertura = list(
        csv.DictReader((directorio / "salidas/cobertura_curricular.csv").open(encoding="utf-8-sig"))
    )
    assert len(cobertura) == 1
    assert re.fullmatch(r"COB_CUR_[0-9a-f]{16}", cobertura[0]["id_cob_curricular"])
    assert cobertura[0]["id_herramienta"]
    cobertura_lineage = [
        json.loads(linea)
        for linea in (directorio / "salidas/reportes/cobertura_curricular_canonica.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert cobertura_lineage[0]["id_logro"] == "LOG_1"
    assert cobertura_lineage[0]["source_ref"] == "curso.docx"
    assert all(
        cobertura_lineage[0][campo]
        for campo in (
            "id_ejecucion",
            "id_competencia_fuente",
            "id_habilidad_fuente",
            "id_herramienta_fuente",
            "id_competencia_canonica",
            "id_habilidad_canonica",
            "id_herramienta_canonica",
        )
    )


def test_no_permite_aprobacion_de_ejecucion_en_curso_o_id_desconocido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    (directorio / "manifest.json").write_text(json.dumps({"estado": "limpiando"}), encoding="utf-8")
    with pytest.raises(aprobaciones.AprobacionNoPermitida, match="terminado"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio, [{"id_pendiente": "PEN_COMP", "decision": "ADD"}]
        )


def test_no_permite_promover_un_pendiente_de_otra_carrera_o_periodo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    filas[0]["carrera"] = "INGENIERIA_DE_SISTEMAS"
    filas[0]["periodo"] = "2030-1"
    ruta.write_text("".join(json.dumps(fila) + "\n" for fila in filas), encoding="utf-8")

    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="alcance"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio,
            [{"id_pendiente": "PEN_COMP", "decision": "ADD"}],
        )


def test_endpoint_expone_y_aplica_el_checkpoint_curricular(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    gestor_api = GestorEjecuciones(directorio.parent)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)

    cliente = TestClient(servidor.app)
    pendientes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    )
    assert pendientes.status_code == 200
    datos_pendientes = pendientes.json()
    assert datos_pendientes["total"] == 2
    paquete = datos_pendientes["paquetes"][0]
    assert {"source_relationships", "relationships", "legacy_rows"}.isdisjoint(paquete)
    assert "provenance" not in paquete["componentes"]["competencias"][0]
    assert "row" not in paquete["filas"][0]
    assert paquete["componentes"]["competencias"][0]["nombre"] == "Diseño omnicanal"
    assert paquete["componentes"]["competencias"][0]["descripcion"] == "Diseñar campañas omnicanal."
    assert paquete["filas"][0]["evidencia"] == ["Diseñar campañas omnicanal."]

    respuesta = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "actor": "revisor@example.com",
            "decisiones": [{"id_pendiente": "PEN_COMP", "decision": "ADD"}],
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["accepted"] == 1

    restantes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    )
    assert restantes.json()["total"] == 1
    assert restantes.json()["filas"][0]["id_pendiente"] == "PEN_TOOL"

    reloaded = GestorEjecuciones(directorio.parent)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", reloaded)
    estado_reiniciado = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}")
    assert estado_reiniciado.status_code == 200
    assert estado_reiniciado.json()["aprobacion_curricular"]["accepted"] == 1


def test_endpoint_acepta_decision_de_paquete_y_expone_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    gestor_api = GestorEjecuciones(directorio.parent)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)
    cliente = TestClient(servidor.app)

    pendientes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    ).json()
    assert pendientes["paquetes_total"] == 1
    assert pendientes["revision"]
    package_id = pendientes["paquetes"][0]["id_paquete_chh"]
    respuesta = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "paquetes": [{"id_paquete_chh": package_id, "decision": "KEEP_PENDING"}],
            "revision": pendientes["revision"],
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["kept_pending_in_request"] == 2


def test_endpoint_descarta_paquete_con_revision_y_motivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", GestorEjecuciones(directorio.parent))
    cliente = TestClient(servidor.app)
    pendientes = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    ).json()

    respuesta = cliente.post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "paquetes": [
                {
                    "id_paquete_chh": pendientes["paquetes"][0]["id_paquete_chh"],
                    "decision": "DISCARD",
                    "reason": "No corresponde al alcance curricular.",
                }
            ],
            "revision": pendientes["revision"],
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["discarded_in_request"] == 2
    activa = cliente.get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    ).json()
    assert activa["paquetes"] == []


def test_endpoint_reutiliza_filas_y_paquetes_completos_para_el_resumen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", GestorEjecuciones(directorio.parent))
    ensamblajes: list[tuple[object, object]] = []
    resumen_entradas: dict[str, object] = {}
    ensamblar_original = aprobaciones._paquetes
    resumen_original = aprobaciones.resumen_aprobacion_curricular

    def contar_ensamblaje(
        directorio: Path, filas: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        paquetes = ensamblar_original(directorio, filas)
        ensamblajes.append((filas, paquetes))
        return paquetes

    def resumir_reutilizando(
        directorio: Path,
        *,
        filas: Sequence[Mapping[str, object]] | None = None,
        paquetes: Sequence[Mapping[str, object]] | None = None,
    ) -> dict[str, object]:
        resumen_entradas.update({"filas": filas, "paquetes": paquetes})
        return resumen_original(directorio, filas=filas, paquetes=paquetes)

    monkeypatch.setattr(aprobaciones, "_paquetes", contar_ensamblaje)
    monkeypatch.setattr(aprobaciones, "resumen_aprobacion_curricular", resumir_reutilizando)

    respuesta = TestClient(servidor.app).get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes?incluir_resueltas=false"
    )

    assert respuesta.status_code == 200
    assert len(ensamblajes) == 1
    assert resumen_entradas["filas"] is ensamblajes[0][0]
    assert resumen_entradas["paquetes"] is ensamblajes[0][1]
    aprobacion = respuesta.json()["aprobacion"]
    assert aprobacion["total"] == 2
    assert aprobacion["paquetes"] == {
        "total": 1,
        "pendientes_por_decidir": 1,
        "accepted": 0,
        "remaining_pending": 1,
    }


def test_paquetes_para_presentacion_api_conserva_revision_visible_sin_provenance_profunda() -> None:
    paquete_completo = {
        "id_paquete_chh": "PKG_CHH_1",
        "package_id": "PKG_CHH_1",
        "source_identity": {
            "id_ejecucion": "NOR_0123456789abcdef",
            "carrera": "Marketing",
            "periodo": "2026-1",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_habilidad_fuente": "HAB_SRC_1",
        },
        "decision": "KEEP_PENDING",
        "requiere_decision": True,
        "decision_state": "PENDING",
        "id_pendientes": ["PEN_COMP"],
        "aliases": [{"id_pendiente": "PEN_ALIAS", "source_identity": {"irrelevante": "x"}}],
        "componentes": {
            "competencias": [
                {
                    "tipo": "competencia",
                    "id_canonico": "COMP_1",
                    "nombre": "Diseño omnicanal",
                    "descripcion": "Diseñar campañas omnicanal.",
                    "canonical": True,
                    "provenance": [{"row": {"payload": "pesado"}}],
                    "row": {"payload": "pesado"},
                }
            ],
            "habilidades": [],
            "herramientas": [],
        },
        "relaciones": [
            {
                "id_curso": "CUR_1",
                "id_silabo": "SIL_1",
                "id_competencia": "COMP_1",
                "id_habilidad": "HAB_1",
                "source_relationships": [{"payload": "pesado"}],
            }
        ],
        "relationships": [{"payload": "pesado"}],
        "source_relationships": [{"payload": "pesado"}],
        "filas": [
            {
                "id_pendiente": "PEN_COMP",
                "tipo": "competencia",
                "archivo": "curso.docx",
                "descripcion_fuente": "Diseñar campañas.",
                "propuesta": {
                    "nombre": "Diseño omnicanal",
                    "descripcion": "Diseñar campañas omnicanal.",
                },
                "evidencia": ["Diseñar campañas omnicanal."],
                "row": {"payload": "pesado"},
                "clasificacion": {"payload": "pesado"},
            }
        ],
        "legacy_rows": [{"payload": "pesado"}],
    }

    presentado = aprobaciones.paquetes_para_presentacion_api([paquete_completo])

    assert presentado[0]["id_paquete_chh"] == "PKG_CHH_1"
    assert presentado[0]["source_identity"]["id_silabo"] == "SIL_1"
    assert presentado[0]["componentes"]["competencias"][0]["nombre"] == "Diseño omnicanal"
    assert (
        presentado[0]["componentes"]["competencias"][0]["descripcion"]
        == "Diseñar campañas omnicanal."
    )
    assert presentado[0]["filas"][0]["evidencia"] == ["Diseñar campañas omnicanal."]
    assert {"source_relationships", "relationships", "legacy_rows"}.isdisjoint(presentado[0])
    assert "provenance" not in presentado[0]["componentes"]["competencias"][0]
    assert "row" not in presentado[0]["filas"][0]
    assert "clasificacion" not in presentado[0]["filas"][0]


def test_presentacion_api_conserva_json_compacto_orden_y_valores() -> None:
    presentado = aprobaciones.filas_para_presentacion_api(
        [
            {
                "id_pendiente": None,
                "tipo": " habilidad \n",
                "decision": None,
                "requiere_decision": False,
                "canonical": 0,
                "propuesta": {
                    "id": 0,
                    "nombre": None,
                    "descripcion": "  texto\ncon espacios  ",
                    "tipo": False,
                },
                "evidencia": [None, 0, False, " \t", "  uno\n dos  ", {"a": 1}, ["x"]],
                "flags": {"f": 1},
                "source_identity": {
                    "id_ejecucion": " NOR_0123456789abcdef ",
                    "carrera": None,
                    "periodo": 0,
                    "id_curso": False,
                    "id_silabo": " SIL_1 ",
                    "id_habilidad_fuente": " \n",
                },
                "provenance": {"deep": "omitted"},
            }
        ]
    )

    assert json.dumps(presentado, ensure_ascii=False, separators=(",", ":")) == (
        '[{"id_pendiente":null,"tipo":" habilidad \\n","decision":null,'
        '"requiere_decision":false,"canonical":0,"propuesta":{"id":0,'
        '"nombre":null,"descripcion":"  texto\\ncon espacios  ","tipo":false},'
        '"evidencia":["uno dos","{\'a\': 1}","[\'x\']"],'
        '"flags":["{\'f\': 1}"],"source_identity":'
        '{"id_ejecucion":"NOR_0123456789abcdef","id_silabo":"SIL_1"}}]'
    )


def test_endpoint_dto_iguala_la_proyeccion_directa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, id_ejecucion = _preparar(tmp_path, monkeypatch)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", GestorEjecuciones(directorio.parent))
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()]
    filas_clasificadas = aprobaciones._filas_clasificadas(directorio)
    paquetes_completos = aprobaciones._paquetes(directorio, filas_clasificadas)
    paquetes_visibles = [
        paquete
        for paquete in paquetes_completos
        if paquete.get("decision") != "DISCARD"
    ]

    respuesta = TestClient(servidor.app).get(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes"
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["filas"] == aprobaciones.filas_para_presentacion_api(filas)
    assert respuesta.json()["paquetes"] == aprobaciones.paquetes_para_presentacion_api(
        paquetes_visibles
    )


def test_endpoint_rechaza_payload_con_listas_de_decision_ambiguas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, id_ejecucion = _preparar(tmp_path, monkeypatch)
    gestor_api = GestorEjecuciones(tmp_path / "ejecuciones")
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)
    respuesta = TestClient(servidor.app).post(
        f"/normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir",
        json={
            "decisiones": [{"id_pendiente": "PEN_COMP", "decision": "KEEP_PENDING"}],
            "paquetes": [{"id_paquete_chh": "PKG_UNKNOWN", "decision": "KEEP_PENDING"}],
        },
    )

    assert respuesta.status_code == 422
    assert "Payload ambiguo" in respuesta.json()["detail"]


def test_relaciones_de_evidencia_no_cruzan_competencias_de_otro_source_package() -> None:
    scope = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_1",
    }
    fila = {**scope, "id_pendiente": "PEN_1"}
    archivos = {
        "catalogo_competencias.csv": [{"id_competencia": "COMP_1"}, {"id_competencia": "COMP_2"}],
        "catalogo_habilidades.csv": [{"id_habilidad": "HAB_1"}],
        "catalogo_herramientas.csv": [],
    }
    fuentes = {
        "competencias_fuente.jsonl": [
            {**scope, "id_competencia_canonica": "COMP_1"},
            {**{**scope, "id_habilidad_fuente": "SRC_2"}, "id_competencia_canonica": "COMP_2"},
        ],
        "habilidades_fuente.jsonl": [{**scope, "id_habilidad_canonica": "HAB_1"}],
        "herramientas_fuente.jsonl": [],
    }
    relaciones: list[dict[str, str]] = []

    aprobaciones._añadir_relaciones_de_evidencia(
        fila,
        "habilidad",
        "HAB_1",
        archivos,
        fuentes,
        relaciones,
    )

    assert [relation["id_competencia"] for relation in relaciones] == ["COMP_1"]


def test_package_decisions_are_independent_per_source_relation_identity() -> None:
    scope = {
        "id_ejecucion": "NOR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "SRC_1",
        "tipo": "habilidad",
        "estado_resolucion": "PENDIENTE_CATALOGACION",
    }
    first = aprobaciones.preparar_fila_paquete(
        {**scope, "id_pendiente": "PEN_REL_1", "id_cob_curricular": "COB_SRC_1"}
    )
    second = aprobaciones.preparar_fila_paquete(
        {**scope, "id_pendiente": "PEN_REL_2", "id_cob_curricular": "COB_SRC_2"}
    )

    expanded = aprobaciones._expandir_decisiones_de_paquete(
        [{"id_paquete_chh": first["id_paquete_chh"], "decision": "KEEP_PENDING"}],
        [first, second],
    )

    assert first["id_paquete_chh"] != second["id_paquete_chh"]
    assert expanded == [
        {
            "id_pendiente": "PEN_REL_1",
            "decision": "KEEP_PENDING",
            "id_paquete_chh": first["id_paquete_chh"],
        }
    ]


def test_escritura_hitl_de_relaciones_preserva_lineage_del_jsonl(
    tmp_path: Path,
) -> None:
    salida = tmp_path / "salidas"
    reportes = salida / "reportes"
    relacion = {
        "id_cob_curricular": "COB_CUR_1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_competencia": "COMP_1",
        "id_habilidad": "HAB_1",
        "id_herramienta": "HERR_1",
    }
    _csv(salida / "cobertura_curricular.csv", aprobaciones.COBERTURA_SCHEMA)
    with (salida / "cobertura_curricular.csv").open("a", encoding="utf-8", newline="") as archivo:
        csv.DictWriter(
            archivo,
            fieldnames=aprobaciones.COBERTURA_SCHEMA,
        ).writerow(relacion)
    reportes.mkdir(parents=True)
    (reportes / "cobertura_curricular_canonica.jsonl").write_text(
        json.dumps(
            {
                **relacion,
                "id_ejecucion": "NOR_0123456789abcdef",
                "id_logro": "LOG_1",
                "id_competencia_fuente": "COMP_SRC_1",
                "id_habilidad_fuente": "HAB_SRC_1",
                "id_herramienta_fuente": "HERR_SRC_1",
                "id_competencia_canonica": "COMP_1",
                "id_habilidad_canonica": "HAB_1",
                "id_herramienta_canonica": "HERR_1",
                "source_ref": "entrada/silabo.pdf#LOG_1",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    relaciones = aprobaciones._cargar_relaciones(salida, reportes)
    aprobaciones._escribir_relaciones(salida, reportes, relaciones)

    persistida = json.loads(
        (reportes / "cobertura_curricular_canonica.jsonl").read_text(encoding="utf-8")
    )
    assert persistida["id_logro"] == "LOG_1"
    assert persistida["source_ref"] == "entrada/silabo.pdf#LOG_1"


def test_clasifica_repetidas_exactas_semanticas_y_herramienta_no_relacionada() -> None:
    filas = aprobaciones.clasificar_propuestas(
        [
            {
                "id_pendiente": "PEN_EXACT_2",
                "tipo": "competencia",
                "propuesta": {
                    "nombre": "Gestión de campañas",
                    "descripcion": "Diseñar campañas.",
                },
                "evidencia": ["Diseñar campañas."],
                "confianza": 0.91,
            },
            {
                "id_pendiente": "PEN_EXACT_1",
                "tipo": "competencia",
                "propuesta": {
                    "nombre": "Gestión de campañas",
                    "descripcion": "Gestionar campañas.",
                },
                "evidencia": ["Gestionar campañas."],
                "confianza": 0.62,
            },
            {
                "id_pendiente": "PEN_SEM_1",
                "tipo": "habilidad",
                "propuesta": {
                    "nombre": "Análisis de datos empresariales",
                    "descripcion": "Analizar datos.",
                },
                "evidencia": ["Analizar datos."],
            },
            {
                "id_pendiente": "PEN_SEM_2",
                "tipo": "habilidad",
                "propuesta": {
                    "nombre": "Análisis de datos comerciales",
                    "descripcion": "Analizar datos.",
                },
                "evidencia": ["Analizar datos."],
            },
            {
                "id_pendiente": "PEN_TOOL",
                "tipo": "herramienta",
                "propuesta": {"nombre": "Slack", "descripcion": "Herramienta de colaboración."},
                "evidencia": ["Evaluar estados financieros."],
            },
        ]
    )

    por_id = {fila["id_pendiente"]: fila for fila in filas}
    assert por_id["PEN_EXACT_1"]["duplicado_exacto"] is True
    assert por_id["PEN_EXACT_2"]["duplicado_exacto"] is True
    assert (
        por_id["PEN_EXACT_1"]["grupo_duplicado_exacto"]
        == por_id["PEN_EXACT_2"]["grupo_duplicado_exacto"]
    )
    assert por_id["PEN_EXACT_2"]["auto_deduplicated"] is False
    assert por_id["PEN_EXACT_2"]["exact_duplicate_representative_id"] == "PEN_EXACT_2"
    assert por_id["PEN_EXACT_2"]["requiere_decision"] is True
    assert por_id["PEN_EXACT_1"]["auto_deduplicated"] is True
    assert por_id["PEN_EXACT_1"]["exact_duplicate_representative_id"] == "PEN_EXACT_2"
    assert por_id["PEN_EXACT_1"]["estado_resolucion"] == "AUTO_DEDUPLICADA"
    assert por_id["PEN_EXACT_1"]["requiere_decision"] is False
    assert por_id["PEN_EXACT_1"]["clasificacion"]["requires_human_decision"] is False
    assert por_id["PEN_SEM_1"]["posible_duplicado_semantico"] is True
    assert por_id["PEN_SEM_2"]["posible_duplicado_semantico"] is True
    assert por_id["PEN_TOOL"]["herramienta_no_relacionada"] is True
    assert "SUSPICIOUS_UNRELATED_TOOL" in por_id["PEN_TOOL"]["flags"]
    assert {fila["id_pendiente"] for fila in filas} == {
        "PEN_EXACT_1",
        "PEN_EXACT_2",
        "PEN_SEM_1",
        "PEN_SEM_2",
        "PEN_TOOL",
    }


def test_deduplicacion_exacta_se_limita_al_paquete_fuente_y_no_cruza_cursos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    pendientes = [
        {
            "id_pendiente": "PEN_EXACT_REP",
            "tipo": "competencia",
            "id_curso": "CUR_1",
            "id_silabo": "SIL_1",
            "id_habilidad_fuente": "SRC_1",
            "propuesta": {"nombre": "Gestión de campañas", "descripcion": "Diseñar."},
            "evidencia": ["Diseñar campañas omnicanal."],
            "confianza": 0.95,
        },
        {
            "id_pendiente": "PEN_EXACT_SUPPRESSED",
            "tipo": "competencia",
            "id_curso": "CUR_2",
            "id_silabo": "SIL_2",
            "id_habilidad_fuente": "SRC_2",
            "propuesta": {"nombre": "Gestión de campañas", "descripcion": "Gestionar."},
            "evidencia": ["Gestionar campañas omnicanal."],
            "confianza": 0.40,
        },
        {
            "id_pendiente": "PEN_SEM_1",
            "tipo": "habilidad",
            "id_curso": "CUR_3",
            "id_silabo": "SIL_3",
            "id_habilidad_fuente": "SRC_3",
            "propuesta": {"nombre": "Analizar datos empresariales"},
            "evidencia": ["Analizar datos."],
        },
        {
            "id_pendiente": "PEN_SEM_2",
            "tipo": "habilidad",
            "id_curso": "CUR_4",
            "id_silabo": "SIL_4",
            "id_habilidad_fuente": "SRC_4",
            "propuesta": {"nombre": "Analizar datos comerciales"},
            "evidencia": ["Analizar datos."],
        },
    ]
    (directorio / "salidas/reportes/pendientes_curriculares.jsonl").write_text(
        "".join(json.dumps(fila) + "\n" for fila in pendientes),
        encoding="utf-8",
    )

    cola = aprobaciones.pendientes_para_revision(directorio)
    assert {fila["id_pendiente"] for fila in cola} == {
        "PEN_EXACT_REP",
        "PEN_EXACT_SUPPRESSED",
        "PEN_SEM_1",
        "PEN_SEM_2",
    }
    resumen = aprobaciones.resumen_aprobacion_curricular(directorio)
    assert resumen["pendientes_por_decidir"] == 4
    assert resumen["remaining_pending"] == 4
    assert resumen["clasificacion"]["auto_deduplicated_rows"] == 0

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [{"id_pendiente": "PEN_EXACT_REP", "decision": "ADD"}],
    )
    aprobacion = resultado["aprobacion"]
    assert aprobacion["pendientes_por_decidir"] == 3
    assert aprobacion["remaining_pending"] == 3
    assert aprobacion["release_gate"]["checks"]["approval"]["pending_decision"] == 3
    assert "PENDING_DECISIONS" in aprobacion["release_gate"]["blockers"]

    persistidas = [
        json.loads(line)
        for line in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    independiente = next(
        fila for fila in persistidas if fila["id_pendiente"] == "PEN_EXACT_SUPPRESSED"
    )
    assert independiente["evidencia"] == ["Gestionar campañas omnicanal."]
    assert independiente["auto_deduplicated"] is False

    aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_EXACT_SUPPRESSED", "decision": "ADD"},
            {"id_pendiente": "PEN_SEM_1", "decision": "KEEP_PENDING"},
            {"id_pendiente": "PEN_SEM_2", "decision": "KEEP_PENDING"},
        ],
    )
    competencias = list(
        csv.DictReader(
            (directorio / "salidas/catalogo_competencias.csv").open(encoding="utf-8-sig")
        )
    )
    assert [fila["nombre_competencia"] for fila in competencias] == ["Gestión de campañas"]


def test_no_materializa_csv_canónico_si_cobertura_fuente_sigue_incompleta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validacion = ResultadoValidacionSilabos(
        archivo="curso.docx",
        carrera="MARKETING",
        periodo="2026-1",
        sha256="entrada",
        valida=True,
        archivos=(ArchivoSilabo("curso.docx", "docx", 1),),
        hallazgos=(),
    )
    registro = {
        "id_silabo": "SIL_1",
        "id_curso": "CUR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "origen": {"archivo": "curso.docx", "formato": "docx"},
        "datos": {
            "curso": "Marketing",
            "logros_especificos": [{"orden": "L1", "descripcion": "Analizar campañas."}],
            "competencias_declaradas": [],
            "herramientas_evidencia": [],
        },
    }
    id_habilidad_fuente = analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", "Analizar campañas.")
    resultado = DecisionCurricular(
        id_habilidad_fuente=id_habilidad_fuente,
        competencia=ConceptoPropuesto(
            nombre="Diseño omnicanal", descripcion="Diseñar campañas omnicanal."
        ),
        habilidad=ConceptoPropuesto(nombre="Analizar campañas", descripcion="Analizar campañas."),
        evidencia=["Analizar campañas."],
        confianza=0.9,
    )

    construir_salidas_curriculares(
        [registro],
        validacion,
        tmp_path / "NOR_0123456789abcdef",
        CatalogoCHH((), (), (), {}, ("test",), "catalogo-v1"),
        propuestas_llm={id_habilidad_fuente: resultado},
    )

    salida = tmp_path / "NOR_0123456789abcdef" / "salidas"
    reportes = salida / "reportes"
    assert (reportes / "competencias_fuente.jsonl").is_file()
    assert (reportes / "pendientes_curriculares.jsonl").is_file()
    assert (reportes / "candidatos_curriculares.json").is_file()
    assert not any((salida / nombre).exists() for nombre, _ in aprobaciones.ARCHIVOS_SALIDA)
    politica = json.loads((reportes / "candidatos_curriculares.json").read_text())[
        "decision_policy"
    ]
    assert politica["exact_duplicates"] == "AUTO_DEDUPLICATE"
    assert politica["semantic_duplicates"] == "REVIEW_ONLY"
    assert politica["suspicious_tools"] == "REVIEW_ONLY"
    assert politica["auto_delete"] is False
    assert politica["auto_merge"] is False

    (tmp_path / "NOR_0123456789abcdef" / "manifest.json").write_text(
        json.dumps(
            {
                "id_ejecucion": "NOR_0123456789abcdef",
                "tipo": "silabos",
                "estado": "limpiado",
                "parametros": {"carrera": "MARKETING", "periodo": "2026-1"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(aprobaciones, "ruta_catalogos", lambda: tmp_path / "catalogos")
    gestor_api = GestorEjecuciones(tmp_path)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor_api)
    filas = [
        json.loads(line)
        for line in (reportes / "pendientes_curriculares.jsonl").read_text().splitlines()
    ]
    cliente = TestClient(servidor.app)
    pendientes = cliente.get(
        "/normalizador/ejecuciones/NOR_0123456789abcdef/pendientes?incluir_resueltas=false"
    )
    assert pendientes.status_code == 200
    assert pendientes.json()["total"] == 2
    respuesta = cliente.post(
        "/normalizador/ejecuciones/NOR_0123456789abcdef/pendientes/decidir",
        json={
            "actor": "test",
            "decisiones": [
                {
                    "id_pendiente": fila["id_pendiente"],
                    "decision": "ADD" if fila["tipo"] == "competencia" else "KEEP_PENDING",
                }
                for fila in filas
            ],
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["aprobacion"]["pendientes_por_decidir"] == 0
    gate = respuesta.json()["aprobacion"]["release_gate"]
    assert gate["decision"] == "BLOCK_IMPORT"
    assert "STRUCTURAL_ERRORS_PRESENT" in gate["blockers"]
    assert not any((salida / nombre).exists() for nombre, _ in aprobaciones.ARCHIVOS_SALIDA)
    assert (
        json.loads((reportes / "candidatos_curriculares.json").read_text())["materialized"] is False
    )


def test_add_de_habilidad_sin_competencia_no_contamina_catalogos_ni_perfil(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    skill_only = {
        "id_pendiente": "PEN_SKILL_ONLY",
        "tipo": "habilidad",
        "estado_resolucion": "PENDIENTE_AMPLIACION_PERFIL",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_logro": "LOG_1",
        "archivo": "curso.docx",
        "id_habilidad_fuente": "HAB_SRC_1",
        "descripcion_fuente": "Analizar campañas.",
        "propuesta": {"nombre": "Analizar campañas", "descripcion": "Analizar campañas."},
        "evidencia": ["Analizar campañas."],
    }
    ruta.write_text(json.dumps(skill_only) + "\n", encoding="utf-8")

    with pytest.raises(aprobaciones.DecisionCurricularInvalida, match="habilidad.*competencia"):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio, [{"id_pendiente": "PEN_SKILL_ONLY", "decision": "ADD"}]
        )

    habilidades = list(
        csv.DictReader((directorio / "salidas/catalogo_habilidades.csv").open(encoding="utf-8-sig"))
    )
    assert habilidades == []
    assert not (tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1").exists()


def test_add_de_herramienta_sin_cadena_chh_no_contamina_catalogos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    tool_only = json.loads(ruta.read_text(encoding="utf-8").splitlines()[1])
    ruta.write_text(json.dumps(tool_only) + "\n", encoding="utf-8")

    with pytest.raises(
        aprobaciones.DecisionCurricularInvalida,
        match="herramienta.*competencia.*habilidad",
    ):
        aprobaciones.aplicar_decisiones_curriculares(
            directorio, [{"id_pendiente": "PEN_TOOL", "decision": "ADD"}]
        )

    herramientas = list(
        csv.DictReader(
            (directorio / "salidas/catalogo_herramientas.csv").open(encoding="utf-8-sig")
        )
    )
    assert herramientas == []
    assert not (tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1").exists()


def test_add_de_competencia_sola_sigue_siendo_materializable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    competencia = json.loads(ruta.read_text(encoding="utf-8").splitlines()[0])
    ruta.write_text(json.dumps(competencia) + "\n", encoding="utf-8")

    resultado = aprobaciones.aplicar_decisiones_curriculares(
        directorio, [{"id_pendiente": "PEN_COMP", "decision": "ADD"}]
    )

    assert resultado["aprobacion"]["release_gate"]["decision"] == "ALLOW_IMPORT"
    perfil = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    competencias = list(
        csv.DictReader((perfil / "catalogo_competencias.csv").open(encoding="utf-8-sig"))
    )
    assert [fila["nombre_competencia"] for fila in competencias] == ["Diseño omnicanal"]


def test_add_preserva_relaciones_n_a_n_existentes_del_paquete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directorio, _ = _preparar(tmp_path, monkeypatch)
    ruta = directorio / "salidas/reportes/pendientes_curriculares.jsonl"
    competencia, herramienta = [
        json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines()
    ]
    competencia_extra = {
        **competencia,
        "id_pendiente": "PEN_COMP_2",
        "propuesta": {
            "nombre": "Ejecución de campañas",
            "descripcion": "Ejecutar campañas omnicanal.",
            "tipo": "dura",
        },
    }
    habilidad = {
        **competencia,
        "id_pendiente": "PEN_SKILL",
        "tipo": "habilidad",
        "propuesta": {"nombre": "Analizar campañas", "descripcion": "Analizar campañas."},
    }
    ruta.write_text(
        "".join(
            json.dumps(fila) + "\n"
            for fila in (competencia, competencia_extra, habilidad, herramienta)
        ),
        encoding="utf-8",
    )

    aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": "PEN_COMP", "decision": "ADD"},
            {"id_pendiente": "PEN_COMP_2", "decision": "ADD"},
            {"id_pendiente": "PEN_SKILL", "decision": "ADD"},
            {"id_pendiente": "PEN_TOOL", "decision": "ADD"},
        ],
    )

    cobertura = list(
        csv.DictReader((directorio / "salidas/cobertura_curricular.csv").open(encoding="utf-8-sig"))
    )
    relaciones = {
        (fila["id_competencia"], fila["id_habilidad"], fila["id_herramienta"]) for fila in cobertura
    }
    assert len(cobertura) == 4
    assert len(relaciones) == 4
    assert len({fila["id_competencia"] for fila in cobertura}) == 2
    assert len({fila["id_habilidad"] for fila in cobertura}) == 1


def test_approving_literal_program_tools_materializes_catalog_and_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_names = (
        "Infogram",
        "Tableau",
        "Flourish",
        "Datawrapper",
        "Genially",
        "Piktochart",
    )
    program_text = "Implement visualizations with " + ", ".join(tool_names) + "."
    id_habilidad_fuente = analista_llm._hash_id(
        "HAB_SRC", "SIL_1", "1", "Implement visualizations"
    )
    decision = DecisionCurricular(
        id_habilidad_fuente=id_habilidad_fuente,
        competencia=ConceptoPropuesto(nombre="Visual data communication"),
        habilidad=ConceptoPropuesto(nombre="Implement visualizations"),
        herramientas=[
            analista_llm.HerramientaPropuesta(nombre=name, evidencia=name) for name in tool_names
        ],
        evidencia=["Implement visualizations"],
        confianza=0.9,
    )
    registro = {
        "id_silabo": "SIL_1",
        "id_curso": "CUR_1",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "origen": {"archivo": "visual-data.docx", "formato": "docx"},
        "datos": {
            "curso": "Visual data communication",
            "logros_especificos": [
                {"orden": "1", "descripcion": "Implement visualizations"}
            ],
            "competencias_declaradas": [
                {
                    "orden": "1",
                    "nombre": "Visual data communication",
                    "descripcion": "Communicate data visually.",
                }
            ],
            "programa_analitico": [program_text],
        },
    }
    validacion = ResultadoValidacionSilabos(
        archivo="visual-data.docx",
        carrera="MARKETING",
        periodo="2026-1",
        sha256="input",
        valida=True,
        archivos=(ArchivoSilabo("visual-data.docx", "docx", 1),),
        hallazgos=(),
    )
    catalogo = CatalogoCHH(
        competencias=(
            ConceptoCHH("COMP_VISUAL", "Visual data communication", "Communicate data visually."),
        ),
        habilidades=(
            ConceptoCHH("HAB_VISUAL", "Implement visualizations", "Implement visualizations."),
        ),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )
    directorio = tmp_path / "NOR_0123456789abcdef"
    construir_salidas_curriculares(
        [registro],
        validacion,
        directorio,
        catalogo,
        propuestas_llm={id_habilidad_fuente: decision},
    )
    (directorio / "manifest.json").write_text(
        json.dumps(
            {
                "id_ejecucion": "NOR_0123456789abcdef",
                "tipo": "silabos",
                "estado": "limpiado",
                "parametros": {"carrera": "MARKETING", "periodo": "2026-1"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(aprobaciones, "ruta_catalogos", lambda: tmp_path / "catalogos")
    pendientes = [
        json.loads(linea)
        for linea in (directorio / "salidas/reportes/pendientes_curriculares.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    herramientas_pendientes = [fila for fila in pendientes if fila["tipo"] == "herramienta"]

    assert {fila["propuesta"]["nombre"] for fila in herramientas_pendientes} == set(tool_names)
    assert len(herramientas_pendientes) == len(tool_names)
    assert all(fila["propuesta"]["descripcion"] for fila in herramientas_pendientes)
    assert all(
        fila["evidencia_provenance"]
        == {
            "origen": "programa_analitico",
            "seccion": "programa_analitico",
            "texto": program_text,
        }
        for fila in herramientas_pendientes
    )

    resultado_aprobacion = aprobaciones.aplicar_decisiones_curriculares(
        directorio,
        [
            {"id_pendiente": fila["id_pendiente"], "decision": "ADD"}
            for fila in pendientes
        ],
    )
    assert (
        resultado_aprobacion["aprobacion"]["release_gate"]["decision"] == "ALLOW_IMPORT"
    ), resultado_aprobacion["aprobacion"]["release_gate"]

    catalogo_herramientas = list(
        csv.DictReader(
            (directorio / "salidas/catalogo_herramientas.csv").open(encoding="utf-8-sig")
        )
    )
    cobertura = list(
        csv.DictReader((directorio / "salidas/cobertura_curricular.csv").open(encoding="utf-8-sig"))
    )
    fuentes = [
        json.loads(linea)
        for linea in (directorio / "salidas/reportes/herramientas_fuente.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert {fila["nombre_herramienta"] for fila in catalogo_herramientas} == set(tool_names)
    assert len(catalogo_herramientas) == len(tool_names)
    assert all(
        fila["id_herramienta"] and fila["descripcion_breve_herramienta"]
        for fila in catalogo_herramientas
    )
    assert len(cobertura) == len(tool_names)
    assert {fila["id_herramienta"] for fila in cobertura} == {
        fila["id_herramienta"] for fila in catalogo_herramientas
    }
    assert len(fuentes) == len(tool_names)
    assert all(
        fila["id_herramienta_fuente"]
        and fila["origen_fuente"] == "programa_analitico"
        and fila["seccion_fuente"] == "programa_analitico"
        and fila["texto_evidencia"] == program_text
        and fila["estado_resolucion"] == "ACEPTADA_POR_USUARIO"
        for fila in fuentes
    )
