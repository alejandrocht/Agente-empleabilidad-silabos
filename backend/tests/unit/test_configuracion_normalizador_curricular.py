"""Regression contract for immutable, provider-aware curricular configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agente.config import settings
from agente.llm import fabrica
from agente.normalizador import ejecuciones
from agente.normalizador.modelos import ResultadoLimpiezaSilabos, ResultadoValidacionSilabos

# spellchecker:off


def _entorno(**overrides: str) -> dict[str, str]:
    values = {
        "NORMALIZADOR_CURRICULAR_LLM": "true",
        "NORMALIZADOR_CURRICULAR_LLM_PROVIDER": "openai",
        "NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL": "http://localhost:11434/v1",
        "NORMALIZADOR_CURRICULAR_OLLAMA_MODEL": "qwen3.8:27b",
        "NORMALIZADOR_CURRICULAR_OPENAI_MODEL": "gpt-5.6-luna",
        "NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT": "medium",
        "NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS": "37",
        "NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES": "5",
        "NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE": "6",
        "NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE": "0.25",
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
    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_OPENAI_MODEL", "process-analyst")

    configuracion = settings.configuracion_normalizador_curricular()

    assert configuracion.modelo_analista == "process-analyst"
    assert configuracion.timeout_llm_seconds == 37


@pytest.mark.parametrize(
    ("key", "value"),
    (("NORMALIZADOR_CURRICULAR_LLM", "definitely"),),
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
    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_OPENAI_MODEL", "mutated-after-snapshot")

    fabrica.obtener_llm(rol, configuracion_curricular=configuracion)

    assert llamada["model"] == configuracion.modelo_para_rol(rol)
    assert llamada["reasoning_effort"] == configuracion.esfuerzo_para_rol(rol)
    assert llamada["timeout"] == configuracion.timeout_llm_seconds
    assert llamada["max_retries"] == configuracion.max_reintentos_llm


def test_fabrica_curricular_usa_ollama_sin_openai_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuracion = settings.configuracion_normalizador_curricular(
        _entorno(
            NORMALIZADOR_CURRICULAR_LLM_PROVIDER="ollama",
            NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL="http://localhost:11434/v1",
            NORMALIZADOR_CURRICULAR_OLLAMA_MODEL="qwen3.8:27b",
        )
    )
    llamada: dict[str, Any] = {}
    monkeypatch.setattr(fabrica, "ChatOpenAI", lambda **kwargs: llamada.update(kwargs) or object())
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fabrica.obtener_llm("analista_curricular", configuracion_curricular=configuracion)

    assert llamada["model"] == "qwen3.8:27b"
    assert llamada["base_url"] == "http://localhost:11434/v1"
    assert llamada["api_key"].get_secret_value() == "ollama"
    assert "reasoning_effort" not in llamada


def test_cambiar_solo_proveedor_selecciona_el_modelo_configurado() -> None:
    entorno = _entorno()

    configuracion_ollama = settings.configuracion_normalizador_curricular(
        {**entorno, "NORMALIZADOR_CURRICULAR_LLM_PROVIDER": "ollama"}
    )
    configuracion_openai = settings.configuracion_normalizador_curricular(
        {**entorno, "NORMALIZADOR_CURRICULAR_LLM_PROVIDER": "openai"}
    )

    assert configuracion_ollama.modelo_analista == "qwen3.8:27b"
    assert configuracion_openai.modelo_analista == "gpt-5.6-luna"


def test_fabrica_curricular_lee_api_key_desde_env_del_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())
    llamada: dict[str, Any] = {}
    monkeypatch.setattr(fabrica, "ChatOpenAI", lambda **kwargs: llamada.update(kwargs) or object())
    monkeypatch.setattr(fabrica, "dotenv_values", lambda _ruta: {"OPENAI_API_KEY": "file-key"})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fabrica.obtener_llm("analista_curricular", configuracion_curricular=configuracion)

    assert llamada["api_key"].get_secret_value() == "file-key"


def test_fabrica_curricular_rechaza_proveedor_desconocido() -> None:
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        settings.configuracion_normalizador_curricular(
            _entorno(NORMALIZADOR_CURRICULAR_LLM_PROVIDER="unknown")
        )


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


def test_snapshot_incluye_todas_las_selecciones_operativas_sin_secretos() -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())

    assert configuracion.a_dict() == {
        "usar_llm": True,
        "proveedor_llm": "openai",
        "base_url_llm": "",
        "modelo_analista": "gpt-5.6-luna",
        "esfuerzo_analista": "medium",
        "timeout_llm_seconds": 37.0,
        "max_reintentos_llm": 5,
        "tamano_lote_llm": 6,
        "temperatura_llm": 0.25,
        "modo_analista": "technical",
        "ruta_catalogo_tecnico": str(
            settings.BASE_DIR / "catalogos" / "carrera_competencia_oficial.csv"
        ),
    }


def test_curriculum_configuration_uses_official_career_competency_map() -> None:
    configuracion = settings.configuracion_normalizador_curricular(_entorno())

    assert configuracion.ruta_catalogo_tecnico == str(
        settings.BASE_DIR / "catalogos" / "carrera_competencia_oficial.csv"
    )


def test_retired_mode_and_external_catalog_path_are_ignored() -> None:
    configuracion = settings.configuracion_normalizador_curricular(
        _entorno(
            NORMALIZADOR_CURRICULAR_ANALYST_MODE="legacy",
            NORMALIZADOR_CURRICULAR_TECHNICAL_CATALOG_PATH="/tmp/retired.xlsx",
        )
    )

    assert configuracion.modo_analista == "technical"
    assert configuracion.ruta_catalogo_tecnico != "/tmp/retired.xlsx"


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

    def limpiar_falso(*_args: object, **kwargs: object) -> ResultadoLimpiezaSilabos:
        monkeypatch.setenv("NORMALIZADOR_CURRICULAR_OPENAI_MODEL", "changed-during-run")
        llamada.update(kwargs)
        return ResultadoLimpiezaSilabos(0, (), (), publicable=True)

    monkeypatch.setattr(ejecuciones, "configuracion_normalizador_curricular", lambda: configuracion)
    monkeypatch.setattr(ejecuciones, "validar_silabos", lambda *_: validacion)
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
        _entorno(NORMALIZADOR_CURRICULAR_OPENAI_MODEL="first")
    )
    segunda = settings.configuracion_normalizador_curricular(
        _entorno(NORMALIZADOR_CURRICULAR_OPENAI_MODEL="second")
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
    assert configuration.modelo_para_rol("analista_curricular") == "gpt-5.6-luna"
    assert not any("residual" in key for key in configuration.a_dict())


# spellchecker:on
