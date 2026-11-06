"""Contrato System One, cacheo auditable y gate de clasificación laboral."""

import csv
import json
import urllib.error
from pathlib import Path

import pytest

from agente.normalizador.empleabilidad.analista_habilidades import ErrorAnalisisHabilidades
from agente.normalizador.empleabilidad.clasificador_clef import ClasificadorClef
from agente.normalizador.empleabilidad.hab_tec_retriever import (
    HabTecMatch,
    HabTecRetriever,
    _Documento,
)
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.modelos import ResultadoValidacionEntrada

FUNCIONES = "Analizar estados financieros. Elaborar presupuestos."


def candidato(i):
    return HabTecMatch(f"H{i}", "Economía", f"Habilidad {i}", "Elaborar presupuestos", 0.8)


def respuesta(body, scores=None):
    data = json.loads(body)
    return {
        "answers": {
            key: {"type": "noul", "noul": (scores or {}).get(key, 0.9)} for key in data["questions"]
        }
    }


def test_clasifica_mas_de_ocho_cachea_aprobados_y_descartes(tmp_path, monkeypatch):
    monkeypatch.setenv("NORMALIZADOR_EMPLEABILIDAD_CLEF_BATCH_SIZE", "6")
    requests = []

    def solicitar(self, body):
        requests.append(json.loads(body))
        return respuesta(body, {"h_0": 0.1})

    monkeypatch.setattr(ClasificadorClef, "_solicitar", solicitar)
    classifier = ClasificadorClef(tmp_path)
    candidates = tuple(candidato(i) for i in range(18))
    first = classifier.seleccionar(FUNCIONES, "Economía", candidates)
    second = classifier.seleccionar(FUNCIONES, "Economía", candidates)
    assert first == second
    assert len(first) == 15
    assert len(requests) == 3
    assert all(r["state"] == {"funciones": FUNCIONES} for r in requests)
    assert all(h.evidencia == FUNCIONES and h.probabilidad == 0.9 for h in first)
    assert all(t["desde_cache"] for t in classifier.ultima_auditoria)
    assert sum(len(t["decisiones"]) for t in classifier.ultima_auditoria) == 18
    assert sum(not d["aceptada"] for t in classifier.ultima_auditoria for d in t["decisiones"]) == 3
    cached = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert cached["respuesta"]["answers"]["h_0"]["noul"] == 0.1


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"answers": {}},
        {"answers": {"ajena": {"type": "noul", "noul": 0.9}}},
        {"answers": {"h_0": {"type": "choice", "noul": 0.9}}},
        *[
            {"answers": {"h_0": {"type": "noul", "noul": value}}}
            for value in [True, "0.9", None, float("nan"), 1.1, -0.1]
        ],
    ],
)
def test_respuesta_invalida_no_aprueba_ni_cachea(tmp_path, monkeypatch, invalid):
    monkeypatch.setattr(ClasificadorClef, "_solicitar", lambda self, body: invalid)
    classifier = ClasificadorClef(tmp_path)
    with pytest.raises(ErrorAnalisisHabilidades):
        classifier.seleccionar(FUNCIONES, "Economía", (candidato(0),))
    assert not list(tmp_path.glob("*.json"))
    assert classifier.ultima_auditoria[-1]["estado"] == "error"


def test_divide_entrada_grande_sin_truncar_funciones(monkeypatch):
    from agente.normalizador.empleabilidad import clasificador_clef as modulo

    classifier = ClasificadorClef()
    candidates = [candidato(i) for i in range(4)]
    limit = (
        len(json.dumps(classifier._payload(FUNCIONES, candidates[:2]), ensure_ascii=False).encode())
        - 1
    )
    monkeypatch.setattr(modulo, "MAX_BYTES", limit)
    bodies = []

    def solicitar(self, body):
        assert len(body) <= limit
        bodies.append(json.loads(body))
        return respuesta(body)

    monkeypatch.setattr(ClasificadorClef, "_solicitar", solicitar)
    assert len(classifier.seleccionar(FUNCIONES, "Economía", candidates)) == 4
    assert len(bodies) == 4
    assert all(b["state"]["funciones"] == FUNCIONES for b in bodies)
    with pytest.raises(ErrorAnalisisHabilidades, match="no se truncó"):
        classifier.seleccionar(FUNCIONES * limit, "Economía", (candidato(0),))


def test_transporte_caido_no_se_convierte_en_cero_habilidades(monkeypatch):
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("sin servicio")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    with pytest.raises(ErrorAnalisisHabilidades):
        ClasificadorClef().seleccionar(FUNCIONES, "Economía", (candidato(0),))


def test_id_compartido_conserva_contexto_con_mayor_probabilidad(monkeypatch):
    a = candidato(1)
    b = HabTecMatch(a.id_habilidad, "Administración", a.nombre, "Otro contexto", 0.7)
    monkeypatch.setattr(
        ClasificadorClef,
        "_solicitar",
        lambda self, body: respuesta(body, {"h_0": 0.6, "h_1": 0.95}),
    )
    result = ClasificadorClef().seleccionar(FUNCIONES, "Economía, Administración", (a, b))
    assert len(result) == 1
    assert result[0].candidato == b
    assert result[0].probabilidad == 0.95


@pytest.mark.parametrize("falla", [False, True])
def test_pipeline_usa_clef_por_defecto_y_no_recorta_ocho(tmp_path: Path, monkeypatch, falla):
    tmp_path = tmp_path / "ejecucion"
    tmp_path.mkdir()
    documents = tuple(
        _Documento(f"H{i}", "Economía", f"Habilidad {i}", "Elaborar presupuestos", (1.0, 0.0))
        for i in range(14)
    )
    retriever = HabTecRetriever(
        documents, endpoint="http://unused", modelo="unused", similitud_minima=0.35, limite=1
    )
    monkeypatch.setattr(HabTecRetriever, "_embedding", lambda self, text: (1.0, 0.0))

    def solicitar(self, body):
        if falla:
            raise ErrorAnalisisHabilidades("Clef no disponible")
        return respuesta(body)

    monkeypatch.setattr(ClasificadorClef, "_solicitar", solicitar)
    (tmp_path / "limpios").mkdir()
    source = {
        "datos": {
            "identificacion": "123",
            "ruc": "20100000000",
            "razon_social": "Empresa",
            "cargo": "Analista",
            "carrera_resumen": "Economía",
            "funciones": FUNCIONES,
        }
    }
    (tmp_path / "limpios/publicaciones.jsonl").write_text(json.dumps(source), encoding="utf-8")
    result = normalizar_staging(
        tmp_path,
        ResultadoValidacionEntrada("fuente.xlsx", "hash", True, (), ()),
        hab_tec_retriever=retriever,
    )
    report = tmp_path / "salidas/reportes/clasificacion_clef.jsonl"
    trace = json.loads(report.read_text(encoding="utf-8"))
    assert trace["configuracion"]["modelo"]
    if falla:
        assert not result.publicable
        assert result.relaciones == 0
        assert any(h.codigo == "HAB_TEC_ANALISIS_ERROR" for h in result.hallazgos)
        assert trace["lotes"][0]["estado"] == "error"
        return
    assert result.publicable
    assert result.relaciones == 14
    assert len(trace["lotes"][0]["decisiones"]) == 14
    with (tmp_path / "salidas/requerimiento_laboral.csv").open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len({r["id_habilidad"] for r in rows}) == 14


def test_umbral_nuevo_no_reutiliza_aprobacion_previa(tmp_path, monkeypatch):
    calls = []

    def solicitar(self, body):
        calls.append(body)
        return respuesta(body, {"h_0": 0.6})

    monkeypatch.setattr(ClasificadorClef, "_solicitar", solicitar)
    monkeypatch.setenv("NORMALIZADOR_EMPLEABILIDAD_CLEF_THRESHOLD", "0.5")
    assert len(ClasificadorClef(tmp_path).seleccionar(FUNCIONES, "Economía", (candidato(0),))) == 1
    monkeypatch.setenv("NORMALIZADOR_EMPLEABILIDAD_CLEF_THRESHOLD", "0.8")
    assert ClasificadorClef(tmp_path).seleccionar(FUNCIONES, "Economía", (candidato(0),)) == ()
    assert len(calls) == 2
