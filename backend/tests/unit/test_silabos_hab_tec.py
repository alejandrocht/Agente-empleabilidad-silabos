"""Closed HAB_TEC vocabulary at retrieval, inference and publication boundaries."""

from __future__ import annotations

import csv
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from agente.config.settings import configuracion_normalizador_curricular
from agente.normalizador.catalogo_hab_tec import GestorCatalogosHabTec
from agente.normalizador.empleabilidad.hab_tec_retriever import (
    ErrorHabTecRetriever,
    HabTecRetriever,
    cargar_retriever_hab_tec,
)
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.silabos import analista_tecnico, salida_catalogos

CARRERA = "Ingeniería de Sistemas"
NOMBRE = "Arquitectura de software"
DESCRIPCION = "Diseña estructuras y patrones técnicos."
LOGRO = "Diseña arquitecturas de software mantenibles."


def _vectorizar(
    base: Path, monkeypatch: pytest.MonkeyPatch, id_habilidad: str = "HAB_TEC_001"
) -> Path:
    fuente = base.parent / "entrada.xlsx"
    libro = Workbook()
    hoja = libro.active
    assert hoja is not None
    hoja.append(["Carrera", "id", "nombre", "descripcion"])
    hoja.append([CARRERA, id_habilidad, NOMBRE, DESCRIPCION])
    hoja.append([CARRERA, "HAB_TEC_002", "Redes", "Configura redes informáticas."])
    hoja.append(["Marketing", id_habilidad, "Analítica comercial", "Analiza campañas."])
    libro.save(fuente)
    gestor = GestorCatalogosHabTec(base, publicar_en_neo4j=lambda *_args: {})
    estado = gestor.crear_desde_archivo(fuente.name, fuente)
    catalogo = gestor._obtener(str(estado["id_catalogo"]))
    catalogo.modelo_embedding = "modelo-del-indice"
    monkeypatch.setattr(gestor, "_embeddings", lambda *_args: [[1, 0], [0, 1], [1, 0]])
    gestor._vectorizar(catalogo)
    assert catalogo.estado == "vectorizado"
    return catalogo.directorio


@pytest.fixture
def indice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "hab_tec"
    monkeypatch.setenv("NORMALIZADOR_HAB_TEC_DIR", str(base))
    monkeypatch.setenv("NORMALIZADOR_HAB_TEC_EMBEDDING_MODEL", "otro-modelo-configurado")
    monkeypatch.setenv("NORMALIZADOR_HAB_TEC_RETRIEVAL_MIN_SIMILARITY", "0.5")
    monkeypatch.setattr(HabTecRetriever, "_embedding", lambda *_args: (1.0, 0.0))
    return _vectorizar(base, monkeypatch)


def _registro(id_silabo: str = "SIL_1") -> dict[str, Any]:
    return {
        "id_curso": "CUR_" + id_silabo,
        "id_silabo": id_silabo,
        "carrera": "INGENIERIA_DE_SISTEMAS",
        "periodo": "2026-2",
        "datos": {
            "nombre_curso": NOMBRE,
            "logro_general": LOGRO,
            "competencias_declaradas": [],
        },
    }


def _propuesta(ref: str | None = "HAB_TEC_001") -> dict[str, Any]:
    return {
        "catalogo_ref": ref,
        "nombre_competencia": "Nombre inventado por el modelo",
        "descripcion_breve_competencia": "Descripción alterada por el modelo.",
        "logros": [LOGRO],
        "evidencia": [{"fuente": "logro", "fragmento": LOGRO}],
        "justificacion": "El logro sustenta la habilidad seleccionada.",
    }


def _modelo(monkeypatch: pytest.MonkeyPatch, respuestas: list[dict[str, Any]]) -> list[Any]:
    llamadas: list[Any] = []

    class Modelo:
        def with_structured_output(self, *_args: Any, **_kwargs: Any) -> Modelo:
            return self

        def invoke(self, mensajes: Any) -> dict[str, Any]:
            llamadas.append(mensajes)
            return deepcopy(respuestas.pop(0) if len(respuestas) > 1 else respuestas[0])

    monkeypatch.setattr(analista_tecnico, "obtener_llm", lambda *_args, **_kwargs: Modelo())
    return llamadas


def _inferir(registros: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, object]]:
    return analista_tecnico.inferir_competencias_tecnicas(
        registros,
        configuracion_normalizador_curricular(
            {
                "NORMALIZADOR_CURRICULAR_LLM": "true",
                "NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS": "120",
                "NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES": "2",
                "NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE": "8",
                "NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE": "0",
                "NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT": "medium",
            }
        ),
        **kwargs,
    )


def test_recupera_por_carrera_y_usa_modelo_del_indice(indice: Path) -> None:
    recuperador = cargar_retriever_hab_tec()
    assert recuperador is not None
    assert recuperador.modelo == "modelo-del-indice"
    assert recuperador.id_catalogo == indice.name
    assert [m.nombre for m in recuperador.buscar(LOGRO, "INGENIERIA_DE_SISTEMAS")] == [NOMBRE]


def test_modelo_selecciona_referencia_y_python_copia_campos_exactos(
    indice: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas = _modelo(monkeypatch, [{"competencias": [_propuesta()]}])
    propuestas = _inferir([_registro()])
    assert len(propuestas) == 1
    assert propuestas[0]["catalogo_ref"] == "HAB_TEC_001"
    assert propuestas[0]["nombre_competencia"] == NOMBRE
    assert propuestas[0]["descripcion_breve_competencia"] == DESCRIPCION
    assert propuestas[0]["catalogo_id"] == indice.name
    assert propuestas[0]["estado_aprobacion"] == "PENDIENTE_APROBACION"
    payload = json.loads(llamadas[0][1][1].split("\n", 1)[1])
    assert [c["catalogo_ref"] for c in payload["catalog_context"]] == ["HAB_TEC_001"]
    assert payload["syllabus_context"]["logros"] == [{"texto": LOGRO}]


@pytest.mark.parametrize("ref", [None, "", "HAB_TEC_999", "HAB_TEC_002"])
def test_rechaza_inventadas_y_referencias_no_recuperadas(
    indice: Path, monkeypatch: pytest.MonkeyPatch, ref: str | None
) -> None:
    llamadas = _modelo(monkeypatch, [{"competencias": [_propuesta(ref)]}])
    auditoria: list[dict[str, object]] = []
    assert _inferir([_registro()], auditoria=auditoria) == []
    assert len(llamadas) == 2
    assert auditoria[0]["codigo"] == "HABILIDAD_FUERA_CATALOGO"


def test_reintento_puede_recuperar_referencia_valida(
    indice: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas = _modelo(
        monkeypatch,
        [
            {"competencias": [_propuesta(None)]},
            {"competencias": [_propuesta()]},
        ],
    )
    assert len(_inferir([_registro()])) == 1
    assert len(llamadas) == 2


def test_misma_habilidad_conserva_evidencia_y_cobertura_de_cada_silabo(
    indice: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _modelo(monkeypatch, [{"competencias": [_propuesta(), _propuesta()]}])
    registros = [_registro(), _registro("SIL_2")]
    propuestas = _inferir(registros)
    assert [p["id_silabo"] for p in propuestas] == ["SIL_1", "SIL_2"]
    assert propuestas[0]["id_propuesta"] != propuestas[1]["id_propuesta"]
    salida = tmp_path / "salida"
    salida_catalogos.construir_catalogos_curriculares(
        registros,
        salida,
        carrera="INGENIERIA_DE_SISTEMAS",
        periodo_academico="2026-2",
        competencias_tecnicas=[{**p, "estado_aprobacion": "APROBADA"} for p in propuestas],
    )
    with (salida / "catalogo_habilidades.csv").open(encoding="utf-8-sig") as archivo:
        habilidades = list(csv.DictReader(archivo))
    assert len(habilidades) == 1
    assert habilidades[0]["id_habilidad"] == "HAB_TEC_001"
    assert habilidades[0]["nombre_habilidad"] == NOMBRE
    assert habilidades[0]["desc_breve"] == DESCRIPCION
    with (salida / "cobertura_curricular.csv").open(encoding="utf-8-sig") as archivo:
        assert {f["id_silabo"] for f in csv.DictReader(archivo)} == {"SIL_1", "SIL_2"}


def test_sin_coincidencias_no_fuerza_propuesta_ni_reintenta(
    indice: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas = _modelo(monkeypatch, [{"competencias": []}])
    auditoria: list[dict[str, object]] = []
    assert _inferir([_registro()], auditoria=auditoria) == []
    assert len(llamadas) == 1
    assert auditoria[0]["severidad"] == "info"


def test_sin_candidatos_o_logros_no_invoca_modelo(
    indice: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamadas = _modelo(monkeypatch, [{"competencias": [_propuesta()]}])
    registro = _registro()
    registro["carrera"] = "Carrera sin catálogo"
    assert _inferir([registro]) == []
    registro = _registro()
    registro["datos"]["logro_general"] = ""
    assert _inferir([registro]) == []
    assert llamadas == []


def test_sin_indice_falla_sin_inventar_catalogo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NORMALIZADOR_HAB_TEC_DIR", str(tmp_path))
    with pytest.raises(ErrorHabTecRetriever, match="No hay un catálogo"):
        _inferir([_registro()])


def test_evidencia_inexistente_es_rechazada(indice: Path, monkeypatch) -> None:
    propuesta = _propuesta()
    propuesta["evidencia"][0]["fragmento"] = "Una evidencia ajena al sílabo."
    _modelo(monkeypatch, [{"competencias": [propuesta]}])
    assert _inferir([_registro()]) == []


def test_cancelacion_se_respeta_entre_silabos(indice: Path, monkeypatch) -> None:
    llamadas = _modelo(monkeypatch, [{"competencias": [_propuesta()]}])
    cancelada = False

    def progreso(traza: Any) -> None:
        nonlocal cancelada
        if traza.estado_analisis == "completado":
            cancelada = True

    with pytest.raises(CancelacionSolicitada):
        _inferir(
            [_registro(), _registro("SIL_2")],
            cancelada=lambda: cancelada,
            al_actualizar_progreso_silabo=progreso,
        )
    assert len(llamadas) == 1


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("catalogo_ref", "HAB_TEC_999"),
        ("catalogo_ref", ""),
        ("nombre_competencia", "arquitectura de software"),
        ("descripcion_breve_competencia", "Descripción editada."),
        ("catalogo_sha256", "sha-alterado"),
    ],
)
def test_exportacion_rechaza_campos_alterados_aun_aprobados(
    indice: Path, monkeypatch, tmp_path: Path, campo: str, valor: str
) -> None:
    _modelo(monkeypatch, [{"competencias": [_propuesta()]}])
    propuesta = _inferir([_registro()])[0]
    propuesta[campo] = valor
    salida = tmp_path / "salida"
    with pytest.raises(ValueError):
        salida_catalogos.construir_catalogos_curriculares(
            [_registro()],
            salida,
            carrera="INGENIERIA_DE_SISTEMAS",
            periodo_academico="2026-2",
            competencias_tecnicas=[{**propuesta, "estado_aprobacion": "APROBADA"}],
        )
    assert not (salida / "catalogo_habilidades.csv").exists()


def test_exportacion_rechaza_habilidad_de_otra_carrera(indice: Path, monkeypatch) -> None:
    catalogo = analista_tecnico.cargar_catalogo_hab_tec()
    propuesta = {
        **_propuesta(),
        "nombre_competencia": "Analítica comercial",
        "descripcion_breve_competencia": "Analiza campañas.",
    }
    with pytest.raises(ValueError, match="idénticos"):
        analista_tecnico.validar_habilidad_catalogo(propuesta, CARRERA, catalogo)


def test_catalogo_nuevo_no_cambia_version_de_propuesta_aprobada(
    indice: Path, monkeypatch, tmp_path: Path
) -> None:
    _modelo(monkeypatch, [{"competencias": [_propuesta()]}])
    propuesta = _inferir([_registro()])[0]
    nuevo = _vectorizar(indice.parent, monkeypatch)
    assert nuevo != indice
    assert cargar_retriever_hab_tec().id_catalogo == nuevo.name
    candidato = analista_tecnico.validar_habilidad_catalogo(propuesta, CARRERA)
    assert candidato.nombre == NOMBRE


@pytest.mark.parametrize(
    "archivo", ["catalogo_normalizado.jsonl", "indice/metadatos.jsonl", "indice/vectores.f32"]
)
def test_indice_inconsistente_bloquea_inferencia(indice: Path, archivo: str) -> None:
    ruta = indice / archivo
    ruta.write_bytes(ruta.read_bytes() + b"alterado")
    with pytest.raises(ErrorHabTecRetriever):
        analista_tecnico.cargar_catalogo_hab_tec()


def test_catalogo_con_vectorizacion_fallida_no_se_activa(indice: Path) -> None:
    ruta = indice / "manifest.json"
    manifest = json.loads(ruta.read_text(encoding="utf-8"))
    manifest["estado"] = "error"
    ruta.write_text(json.dumps(manifest), encoding="utf-8")
    assert cargar_retriever_hab_tec() is None
    with pytest.raises(ErrorHabTecRetriever):
        cargar_retriever_hab_tec(indice.name)


def test_hash_literal_del_catalogo_se_conserva_hasta_importacion(
    indice: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agente.db.neo4j_catalogos import leer_catalogos

    id_habilidad = "f9db583c7660"
    _vectorizar(indice.parent, monkeypatch, id_habilidad)
    _modelo(monkeypatch, [{"competencias": [_propuesta(id_habilidad)]}])
    registro = _registro("1234567890abcdef")
    registro["id_curso"] = "CUR_1234567890abcdef"
    registro["id_silabo"] = "SIL_1234567890abcdef"
    propuestas = _inferir([registro])
    assert propuestas[0]["catalogo_ref"] == id_habilidad
    propuestas[0]["estado_aprobacion"] = "APROBADA"
    salida = tmp_path / "salida_hash"
    salida_catalogos.construir_catalogos_curriculares(
        [registro],
        salida,
        carrera="INGENIERIA_DE_SISTEMAS",
        periodo_academico="2026-2",
        competencias_tecnicas=propuestas,
    )
    filas = leer_catalogos(salida)
    assert filas["catalogo_habilidades.csv"][0]["id_habilidad"] == id_habilidad
    assert filas["catalogo_habilidades.csv"][0]["nombre_habilidad"] == NOMBRE
    assert filas["catalogo_habilidades.csv"][0]["desc_breve"] == DESCRIPCION
    assert {f["id_habilidad"] for f in filas["cobertura_curricular.csv"]} == {id_habilidad}
