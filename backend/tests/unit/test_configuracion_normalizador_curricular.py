"""Regression contract for immutable curricular-normalizer runtime configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agente.config import settings
from agente.llm import fabrica
from agente.normalizador import ejecuciones
from agente.normalizador.embeddings import OpenAIEmbeddingProvider
from agente.normalizador.modelos import ResultadoLimpiezaSilabos, ResultadoValidacionSilabos


def _entorno(**overrides: str) -> dict[str, str]:
    values = {
        "NORMALIZADOR_CURRICULAR_LLM": "true",
        "NORMALIZADOR_CURRICULAR_ANALYST_MODEL": "analyst-model",
        "NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT": "medium",
        "NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS": "37",
        "NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES": "5",
        "NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE": "6",
        "NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE": "0.25",
        "NORMALIZADOR_CURRICULAR_EMBEDDINGS": "true",
        "NORMALIZADOR_CURRICULAR_EMBEDDING_CARRERAS": "MARKETING@2026-1",
        "NORMALIZADOR_CURRICULAR_EMBEDDING_MODEL": "embedding-model",
        "NORMALIZADOR_CURRICULAR_EMBEDDING_MIN_SIMILARITY": "0.2",
        "NORMALIZADOR_CURRICULAR_EMBEDDING_COMPETENCIA_CANDIDATES": "11",
        "NORMALIZADOR_CURRICULAR_EMBEDDING_HABILIDAD_CANDIDATES": "12",
        "NORMALIZADOR_CURRICULAR_EMBEDDING_HERRAMIENTA_CANDIDATES": "13",
        "NORMALIZADOR_CURRICULAR_LEXICAL_COMPETENCIA_CANDIDATES": "4",
        "NORMALIZADOR_CURRICULAR_LEXICAL_HABILIDAD_CANDIDATES": "5",
        "NORMALIZADOR_CURRICULAR_LEXICAL_HERRAMIENTA_CANDIDATES": "6",
        "NORMALIZADOR_CURRICULAR_CONTEXT_EXAMPLE_LIMIT": "3",
    }
    values.update(overrides)
    return values


def test_configuracion_curricular_prefiere_el_proceso_sobre_backend_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(f"{key}={value}" for key, value in _entorno().items()),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    for key in _entorno():
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ANALYST_MODEL", "process-analyst")

    configuracion = settings.configuracion_normalizador_curricular()

    assert configuracion.modelo_analista == "process-analyst"
    assert configuracion.timeout_llm_seconds == 37


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("NORMALIZADOR_CURRICULAR_LLM", "definitely"),
        ("NORMALIZADOR_CURRICULAR_EMBEDDINGS", "sometimes"),
    ),
)
def test_configuracion_curricular_rechaza_booleanos_malformados(key: str, value: str) -> None:
    with pytest.raises(ValueError, match=key):
        settings.configuracion_normalizador_curricular(_entorno(**{key: value}))


@pytest.mark.parametrize(
    "key",
    ("NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT",),
)
def test_configuracion_curricular_rechaza_reasoning_effort_invalido(key: str) -> None:
    with pytest.raises(ValueError, match=key):
        settings.configuracion_normalizador_curricular(_entorno(**{key: "max"}))


@pytest.mark.parametrize(
    "rol",
    ("analista_curricular",),
)
def test_fabrica_curricular_usa_exclusivamente_el_snapshot_por_rol(
    monkeypatch: pytest.MonkeyPatch,
    rol: str,
) -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())
    llamada: dict[str, Any] = {}
    monkeypatch.setattr(fabrica, "ChatOpenAI", lambda **kwargs: llamada.update(kwargs) or object())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ANALYST_MODEL", "mutated-after-snapshot")

    fabrica.obtener_llm(rol, configuracion_curricular=configuracion)

    assert llamada["model"] == configuracion.modelo_para_rol(rol)
    assert llamada["reasoning_effort"] == configuracion.esfuerzo_para_rol(rol)
    assert llamada["timeout"] == configuracion.timeout_llm_seconds
    assert llamada["max_retries"] == configuracion.max_reintentos_llm


def test_fabrica_curricular_no_relee_temperatura_despues_del_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())
    llamada: dict[str, Any] = {}
    monkeypatch.setattr(fabrica, "ChatOpenAI", lambda **kwargs: llamada.update(kwargs) or object())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_TEMPERATURE", "1.75")
    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE", "1.5")

    fabrica.obtener_llm("analista_curricular", configuracion_curricular=configuracion)

    assert llamada["temperature"] == configuracion.temperatura_llm == 0.25


def test_fabrica_curricular_rechaza_un_rol_sin_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(ValueError, match="configuracion_curricular"):
        fabrica.obtener_llm("analista_curricular")


def test_embedding_provider_recibe_modelo_del_snapshot() -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())

    provider = OpenAIEmbeddingProvider(configuracion.modelo_embedding)

    assert provider.model_name == "embedding-model"


def test_snapshot_incluye_todas_las_selecciones_operativas_sin_secretos() -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())

    assert configuracion.a_dict() == {
        "usar_llm": True,
        "modelo_analista": "analyst-model",
        "esfuerzo_analista": "medium",
        "timeout_llm_seconds": 37.0,
        "max_reintentos_llm": 5,
        "tamano_lote_llm": 6,
        "temperatura_llm": 0.25,
        "embeddings_habilitados": True,
        "embedding_carreras": "MARKETING@2026-1",
        "modelo_embedding": "embedding-model",
        "umbral_similitud_embedding": 0.2,
        "limite_embedding_competencia": 11,
        "limite_embedding_habilidad": 12,
        "limite_embedding_herramienta": 13,
        "limite_lexical_competencia": 4,
        "limite_lexical_habilidad": 5,
        "limite_lexical_herramienta": 6,
        "limite_ejemplos_contexto": 3,
    }


def test_configuracion_curricular_admite_lotes_mayores_que_veinte() -> None:
    configuracion = settings.configuracion_normalizador_curricular(
        _entorno(NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE="21")
    )

    assert configuracion.tamano_lote_llm == 21


def test_ejecucion_persiste_y_propaga_el_mismo_snapshot_a_limpieza(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())
    gestor = ejecuciones.GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "paquete.zip")
    ejecucion = gestor._obtener_objeto(id_ejecucion)
    validacion = ResultadoValidacionSilabos(
        archivo="paquete.zip",
        carrera="Marketing",
        periodo="2026-1",
        sha256="sha256",
        valida=True,
        archivos=(),
        hallazgos=(),
    )
    llamada: dict[str, object] = {}

    class CatalogoFalso:
        def resumen(self) -> dict[str, object]:
            return {"disponible": True}

    def limpiar_falso(*_args: object, **kwargs: object) -> ResultadoLimpiezaSilabos:
        monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ANALYST_MODEL", "changed-during-run")
        llamada.update(kwargs)
        return ResultadoLimpiezaSilabos(0, (), (), publicable=True)

    monkeypatch.setattr(ejecuciones, "configuracion_normalizador_curricular", lambda: configuracion)
    monkeypatch.setattr(ejecuciones, "validar_silabos", lambda *_: validacion)
    monkeypatch.setattr(ejecuciones, "cargar_catalogo", CatalogoFalso)
    monkeypatch.setattr(ejecuciones, "cargar_catalogo_carrera", lambda *_: None)
    monkeypatch.setattr(ejecuciones, "limpiar_silabos", limpiar_falso)

    gestor._validar_silabos(
        ejecucion,
        directorio / "entrada" / "paquete.zip",
        "Marketing",
        "2026-1",
    )

    manifest = json.loads((directorio / "manifest.json").read_text(encoding="utf-8"))
    assert llamada["configuracion_curricular"] is configuracion
    assert manifest["configuracion_curricular"] == configuracion.a_dict()
    assert "changed-during-run" not in json.dumps(manifest)


def test_configuracion_curricular_no_filtra_estado_entre_entornos() -> None:
    primera = settings.configuracion_normalizador_curricular(
        _entorno(NORMALIZADOR_CURRICULAR_ANALYST_MODEL="first")
    )
    segunda = settings.configuracion_normalizador_curricular(
        _entorno(NORMALIZADOR_CURRICULAR_ANALYST_MODEL="second")
    )

    assert primera.modelo_analista == "first"
    assert segunda.modelo_analista == "second"


def test_startup_without_retired_residual_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A single analyst needs no second-pass settings, even with stale deployments."""
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    values = {key: value for key, value in _entorno().items() if "RESIDUAL" not in key}
    configuration = settings.configuracion_normalizador_curricular(values)
    assert configuration.modelo_para_rol("analista_curricular") == "analyst-model"
    assert not any("residual" in key for key in configuration.a_dict())
