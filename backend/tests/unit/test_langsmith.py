"""Pruebas offline del seam opcional de trazas LangSmith."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.silabos import analista_llm
from agente.observabilidad import langsmith


def test_configuracion_llm_es_noop_con_tracing_apagado(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    assert langsmith.configuracion_llm("analista_curricular") is None


def test_configuracion_llm_publica_nombre_tags_y_metadata_sin_secretos(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    config = langsmith.configuracion_llm(
        "inspector_curricular",
        id_ejecucion="NOR_123",
        carrera="MARKETING",
        periodo="2026-1",
        chunk=3,
    )

    assert config is not None
    assert config["run_name"] == "normalizador.curricular.inspector_curricular"
    assert "rol:inspector_curricular" in config["tags"]
    assert "carrera:MARKETING" in config["tags"]
    assert "periodo:2026-1" in config["tags"]
    assert config["metadata"] == {
        "observability_schema": "normalizador-curricular/langsmith-v1",
        "execution_id": "NOR_123",
        "career": "MARKETING",
        "period": "2026-1",
        "llm_role": "inspector_curricular",
        "retry": False,
        "chunk": "3",
    }
    assert all("key" not in str(valor).lower() for valor in config.values())


def test_invocar_llm_pasa_config_por_with_config(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    class RunnableFalso:
        def __init__(self) -> None:
            self.config = None

        def with_config(self, config):
            self.config = config
            return self

        def invoke(self, prompt: str):
            return {"prompt": prompt}

    runnable = RunnableFalso()
    respuesta = langsmith.invocar_llm(
        runnable,
        "entrada de dominio",
        rol="analista_curricular",
        id_ejecucion="NOR_123",
        carrera="MARKETING",
        periodo="2026-1",
    )

    assert respuesta == {"prompt": "entrada de dominio"}
    assert runnable.config["run_name"] == "normalizador.curricular.analista_curricular"
    assert runnable.config["metadata"]["execution_id"] == "NOR_123"


def test_ejecutar_flujo_no_requiere_red(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    llamadas = {}

    def traceable(**kwargs):
        llamadas["config"] = kwargs

        def decorar(funcion):
            def trazada(entrada):
                llamadas["entrada"] = entrada
                return funcion(entrada)

            return trazada

        return decorar

    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(traceable=traceable))

    resultado = langsmith.ejecutar_flujo(
        lambda: SimpleNamespace(publicable=True, outputs=("salida",)),
        run_name="normalizador.curricular",
        inputs={"execution_id": "NOR_123", "files_count": 1},
        tags=["normalizador", "curricular"],
        metadata={"execution_id": "NOR_123"},
    )

    assert resultado.publicable is True
    assert llamadas["config"]["name"] == "normalizador.curricular"
    assert llamadas["entrada"] == {"run": "normalizador.curricular"}
    assert llamadas["config"]["process_inputs"](llamadas["entrada"]) == {
        "execution_id": "NOR_123",
        "files_count": 1,
    }
    assert llamadas["config"]["process_outputs"](resultado) == {
        "type": "SimpleNamespace",
        "publicable": True,
        "outputs_count": 1,
    }


def test_ejecutar_flujo_cierra_traza_con_estado_cancelado(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    capturado = {}

    def traceable(**kwargs):
        def decorar(funcion):
            def trazada(entrada):
                resultado = funcion(entrada)
                capturado["salida"] = kwargs["process_outputs"](resultado)
                return resultado

            return trazada

        return decorar

    monkeypatch.setitem(sys.modules, "langsmith", SimpleNamespace(traceable=traceable))

    with pytest.raises(CancelacionSolicitada):
        langsmith.ejecutar_flujo(
            lambda: (_ for _ in ()).throw(CancelacionSolicitada()),
            run_name="normalizador.curricular",
            inputs={"execution_id": "NOR_123"},
            tags=["normalizador"],
            metadata={"execution_id": "NOR_123"},
        )

    assert capturado["salida"]["status"] == "cancelled"
    assert capturado["salida"]["estado"] == "cancelado"


def test_analista_asigna_run_name_y_rol_distinguibles(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    capturado = {}

    class RunnableFalso:
        def with_config(self, config):
            capturado.update(config)
            return self

        def invoke(self, _prompt: str):
            return analista_llm.LoteDecisionesCurriculares()

    class LLMFalso:
        model_name = "modelo-test"

        def with_structured_output(self, _schema):
            return RunnableFalso()

    resultado = analista_llm._invocar_analista(
        LLMFalso(),
        tuple(),
        {},
        "MARKETING",
        "2026-1",
        id_ejecucion="NOR_123",
        chunk=2,
    )

    assert resultado.decisiones == []
    assert capturado["run_name"] == "normalizador.curricular.analista_curricular"
    assert "rol:analista_curricular" in capturado["tags"]
    assert capturado["metadata"]["execution_id"] == "NOR_123"
