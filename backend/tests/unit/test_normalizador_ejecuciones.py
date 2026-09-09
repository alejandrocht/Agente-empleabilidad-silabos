"""Pruebas de cancelación y ciclo de vida del historial del normalizador."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from agente.api import normalizador, servidor
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.modelos import (
    Hallazgo,
    ResultadoLimpiezaSilabos,
    ResultadoNormalizacion,
)


def _gestor_con_ejecucion(tmp_path: Path) -> tuple[GestorEjecuciones, str, Path]:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear(
        "silabos",
        "paquete.zip",
        {"carrera": "Marketing", "periodo": "2026-1"},
    )
    return gestor, id_ejecucion, directorio


def _salidas_curriculares() -> tuple[dict[str, object], ...]:
    return (
        {
            "tipo": "csv_curricular",
            "archivo": "salidas/catalogo_competencias.csv",
            "registros": 1,
        },
        {
            "tipo": "csv_curricular",
            "archivo": "salidas/catalogo_habilidades.csv",
            "registros": 1,
        },
        {
            "tipo": "csv_curricular",
            "archivo": "salidas/catalogo_herramientas.csv",
            "registros": 1,
        },
        {
            "tipo": "csv_curricular",
            "archivo": "salidas/cobertura_curricular.csv",
            "registros": 1,
        },
        {
            "tipo": "candidatos_curriculares",
            "archivo": "salidas/reportes/candidatos_curriculares.json",
            "registros": 4,
        },
        {
            "tipo": "decisiones_curriculares",
            "archivo": "salidas/reportes/decisiones_curriculares.jsonl",
            "registros": 1,
        },
    )


def test_a_dict_oculta_salidas_curriculares_hasta_cerrar_hitl(tmp_path: Path) -> None:
    gestor, id_ejecucion, directorio = _gestor_con_ejecucion(tmp_path)
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    for salida in _salidas_curriculares():
        ruta = directorio / str(salida["archivo"])
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("contenido", encoding="utf-8")
    ejecucion.limpieza_silabos = ResultadoLimpiezaSilabos(
        registros=1,
        outputs=_salidas_curriculares(),
        hallazgos=(),
        release_gate={
            "decision": "BLOCK_IMPORT",
            "checks": {
                "approval": {
                    "canonical_materialized": False,
                    "pending_decision": 1,
                }
            },
        },
    )

    estado = ejecucion.a_dict()

    assert estado["release_gate"]["decision"] == "BLOCK_IMPORT"
    assert estado["outputs"] == []
    assert estado["limpieza_silabos"]["outputs"] == []
    assert id_ejecucion.startswith("NOR_")


def test_a_dict_de_empleabilidad_conserva_sus_outputs(tmp_path: Path) -> None:
    gestor = GestorEjecuciones(tmp_path)
    _id_ejecucion, directorio = gestor.crear("empleabilidad", "fuente.xlsx")
    ejecucion = gestor._obtener_objeto(_id_ejecucion)
    ruta = directorio / "salidas" / "requerimiento_laboral.csv"
    ruta.parent.mkdir(parents=True)
    ruta.write_text("id\nuno\n", encoding="utf-8")
    ejecucion.normalizacion = ResultadoNormalizacion(
        publicable=True,
        registros_procesados={"publicaciones": 1},
        relaciones=1,
        cuarentena=0,
        outputs=(
            {
                "tipo": "requerimiento_laboral",
                "archivo": "salidas/requerimiento_laboral.csv",
                "registros": 1,
            },
        ),
        hallazgos=(),
    )

    estado = ejecucion.a_dict()

    assert [output["archivo"] for output in estado["outputs"]] == [
        "salidas/requerimiento_laboral.csv"
    ]


def test_cancelar_persiste_la_solicitud_y_el_worker_cierra_como_cancelado(
    monkeypatch, tmp_path: Path
) -> None:
    gestor, id_ejecucion, directorio = _gestor_con_ejecucion(tmp_path)
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "limpiando"
    gestor._persistir(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app)

    respuesta = cliente.post(f"/normalizador/ejecuciones/{id_ejecucion}/cancelar")

    assert respuesta.status_code == 202
    assert respuesta.json()["cancelacion_solicitada"] is True
    assert ejecucion.cancelada.is_set()
    assert "no se enviará otro lote" in respuesta.json()["mensaje"]

    gestor._validar_silabos(ejecucion, tmp_path / "paquete.zip", "Marketing", "2026-1")

    estado = gestor.obtener(id_ejecucion)
    assert estado["estado"] == "cancelado"
    assert estado["cancelacion_solicitada"] is True
    assert any(
        hallazgo["codigo"] == "PROCESAMIENTO_CANCELADO" for hallazgo in estado["hallazgos"]
    )
    manifest = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["estado"] == "cancelado"


def test_cancelar_estado_terminal_devuelve_conflicto(monkeypatch, tmp_path: Path) -> None:
    gestor, id_ejecucion, _directorio = _gestor_con_ejecucion(tmp_path)
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "limpiado"
    gestor._persistir(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app)

    respuesta = cliente.post(f"/normalizador/ejecuciones/{id_ejecucion}/cancelar")

    assert respuesta.status_code == 409
    assert "no admite cancelación" in respuesta.json()["detail"]


def test_historial_consolida_reportes_purga_temporales_y_conserva_fuente_curricular(
    tmp_path: Path,
) -> None:
    gestor, id_ejecucion, directorio = _gestor_con_ejecucion(tmp_path)
    for relativo in (
        "entrada/paquete.zip",
        "fuentes_curriculares/uno.pdf",
        "limpios/silabos.jsonl",
    ):
        ruta = directorio / relativo
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("temporal", encoding="utf-8")
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True)
    (reportes / "decisiones_llm.jsonl").write_text(
        '{"estado":"REVISAR","sugerencia":"Revisar herramienta"}\n',
        encoding="utf-8",
    )
    salida = directorio / "salidas" / "cobertura_curricular.csv"
    salida.write_text("id\n1\n", encoding="utf-8")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "cancelado"
    ejecucion.hallazgos = [
        Hallazgo("AVISO", "warning", "Aviso de prueba"),
        Hallazgo("ERROR", "error", "Error de prueba"),
    ]
    gestor._finalizar(ejecucion)

    listado = gestor.listar_historial(20)
    item = next(item for item in listado["ejecuciones"] if item["id_ejecucion"] == id_ejecucion)
    assert item["estado"] == "cancelado"
    assert item["resumen"] == {"advertencias": 1, "errores": 1, "outputs": 0}
    assert (directorio / "entrada" / "paquete.zip").is_file()
    assert not (directorio / "fuentes_curriculares").exists()
    assert not (directorio / "limpios").exists()
    assert salida.exists()

    reporte = gestor.obtener_reporte(id_ejecucion)
    assert reporte["manifest"]["estado"] == "cancelado"
    assert reporte["reportes"] == {}
    assert (reportes / "decisiones_llm.jsonl").read_text(encoding="utf-8") == (
        '{"estado":"REVISAR","sugerencia":"Revisar herramienta"}\n'
    )

    eliminado = gestor.eliminar_historial(id_ejecucion)
    assert eliminado == {"id_ejecucion": id_ejecucion, "eliminado": True}
    assert not directorio.exists()


def test_migra_warning_macos_en_manifests_y_reportes_sin_perder_historial_ni_csv(
    tmp_path: Path,
) -> None:
    """La migración histórica solo quita el warning obsoleto de cada artefacto."""

    id_ejecucion = "NOR_0123456789abcdef"
    timestamp_fixture = datetime.now(UTC).isoformat()
    directorio = tmp_path / id_ejecucion
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True)
    salida = directorio / "salidas" / "cobertura_curricular.csv"
    salida.write_text("id_cob_curricular,id_curso\nCOB_1,CUR_1\n", encoding="utf-8")

    warning_macos = {
        "codigo": "METADATO_MACOS_IGNORADO",
        "severidad": "warning",
        "mensaje": "Se ignoró un archivo auxiliar de macOS dentro del ZIP.",
    }
    warning_valido = {
        "codigo": "ARCHIVO_NO_CURRICULAR",
        "severidad": "warning",
        "mensaje": "Se conservó un warning real.",
    }
    error_valido = {
        "codigo": "ZIP_ILEGIBLE",
        "severidad": "error",
        "mensaje": "Se conservó un error real.",
    }
    manifest = {
        "id_ejecucion": id_ejecucion,
        "tipo": "silabos",
        "archivo": "paquete.zip",
        "parametros": {"carrera": "Marketing", "periodo": "2026-1"},
        "estado": "limpiado_con_advertencias",
            "creada_en": timestamp_fixture,
            "actualizada_en": timestamp_fixture,
        "hallazgos": [warning_macos, warning_valido, error_valido],
        "validacion_silabos": {
            "hallazgos": [warning_macos, warning_valido, error_valido],
        },
        "limpieza_silabos": {"hallazgos": [warning_macos, warning_valido]},
        "outputs": [
            {
                "archivo": "salidas/cobertura_curricular.csv",
                "tipo": "csv_curricular",
                "registros": 1,
            }
        ],
    }
    (directorio / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )
    (reportes / "decisiones_llm.jsonl").write_text(
        "\n".join(
            [
                json.dumps(warning_macos, ensure_ascii=False),
                json.dumps(
                    {
                        "estado": "ACEPTADA",
                        "id_habilidad_fuente": "HAB_1",
                        "justificacion": "Decisión válida preservada.",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (reportes / "resumen.json").write_text(
        json.dumps(
            {"advertencias": 2, "hallazgos": [warning_macos, warning_valido]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # Un reporte incompleto no debe impedir que el gestor arranque ni que lea el resto.
    (reportes / "legado_malformado.json").write_text("{", encoding="utf-8")

    gestor = GestorEjecuciones(tmp_path)

    estado = gestor.obtener(id_ejecucion)
    assert "METADATO_MACOS_IGNORADO" not in json.dumps(estado, ensure_ascii=False)
    assert estado["hallazgos"] == [warning_valido, error_valido]
    assert estado["validacion_silabos"]["hallazgos"] == [warning_valido, error_valido]
    assert estado["limpieza_silabos"]["hallazgos"] == [warning_valido]
    assert estado["estado"] == "limpiado_con_advertencias"

    resumen = gestor.listar_historial()["ejecuciones"][0]
    assert resumen["resumen"] == {"advertencias": 1, "errores": 1, "outputs": 0}
    assert salida.exists()
    assert json.loads((reportes / "resumen.json").read_text(encoding="utf-8")) == {
        "advertencias": 1,
        "hallazgos": [warning_valido],
    }
    reporte = gestor.obtener_reporte(id_ejecucion)
    assert reporte["reportes"] == {}
    decisiones = (reportes / "decisiones_llm.jsonl").read_text(encoding="utf-8")
    assert "METADATO_MACOS_IGNORADO" not in decisiones
    assert "Decisión válida preservada." in decisiones
    assert (reportes / "legado_malformado.json").read_text(encoding="utf-8") == "{"


def test_migracion_macos_recalcula_estado_si_era_el_unico_warning(tmp_path: Path) -> None:
    id_ejecucion = "NOR_fedcba9876543210"
    directorio = tmp_path / id_ejecucion
    directorio.mkdir()
    warning_macos = {
        "codigo": "METADATO_MACOS_IGNORADO",
        "severidad": "warning",
        "mensaje": "Warning legado.",
    }
    (directorio / "manifest.json").write_text(
        json.dumps(
            {
                "id_ejecucion": id_ejecucion,
                "tipo": "silabos",
                "estado": "limpiado_con_advertencias",
                "hallazgos": [warning_macos],
                "outputs": [],
            }
        ),
        encoding="utf-8",
    )

    gestor = GestorEjecuciones(tmp_path)

    assert gestor.obtener(id_ejecucion)["estado"] == "limpiado"
    assert gestor.listar_historial()["ejecuciones"][0]["resumen"]["advertencias"] == 0


def test_endpoints_de_historial_listan_y_descargan_reporte(monkeypatch, tmp_path: Path) -> None:
    gestor, id_ejecucion, directorio = _gestor_con_ejecucion(tmp_path)
    reportes = directorio / "salidas" / "reportes"
    reportes.mkdir(parents=True)
    (reportes / "analisis_llm.json").write_text('{"estado":"COMPLETADO"}', encoding="utf-8")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    ejecucion.estado = "limpiado"
    gestor._finalizar(ejecucion)
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    cliente = TestClient(servidor.app)

    listado = cliente.get("/normalizador/ejecuciones")
    reporte = cliente.get(f"/normalizador/ejecuciones/{id_ejecucion}/reporte")

    assert listado.status_code == 200
    assert any(item["id_ejecucion"] == id_ejecucion for item in listado.json()["ejecuciones"])
    assert reporte.status_code == 200
    assert "attachment" in reporte.headers["content-disposition"]
    assert reporte.json()["reportes"] == {}
    assert (reportes / "analisis_llm.json").read_text(encoding="utf-8") == (
        '{"estado":"COMPLETADO"}'
    )
    eliminado = cliente.delete(f"/normalizador/ejecuciones/{id_ejecucion}/historial")
    assert eliminado.status_code == 200


def test_retencion_lru_conserva_solo_la_ejecucion_terminal_mas_reciente(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("NORMALIZADOR_HISTORIAL_MAX_EJECUCIONES", "1")
    monkeypatch.setenv("NORMALIZADOR_HISTORIAL_RETENCION_DIAS", "99999")
    gestor = GestorEjecuciones(tmp_path)
    primer_id, primer_directorio = gestor.crear("silabos", "primero.zip")
    primer = gestor._obtener_objeto(primer_id)
    primer.estado = "limpiado"
    gestor._finalizar(primer)
    primer.actualizada_en = "2020-01-01T00:00:00+00:00"
    gestor._persistir(primer)

    segundo_id, segundo_directorio = gestor.crear("silabos", "segundo.zip")
    segundo = gestor._obtener_objeto(segundo_id)
    segundo.estado = "limpiado"
    gestor._finalizar(segundo)

    assert not primer_directorio.exists()
    assert segundo_directorio.exists()
    historial = gestor.listar_historial()["ejecuciones"]
    assert [item["id_ejecucion"] for item in historial] == [segundo_id]
