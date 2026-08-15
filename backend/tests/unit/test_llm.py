"""Pruebas de la selección OpenAI por rol y sus fallos claros."""

from __future__ import annotations

import pytest

from agente.llm import fabrica


class ChatOpenAIFalso:
    """Captura argumentos sin abrir red durante las pruebas."""

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def test_modelo_especifico_del_rol(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "modelo-global")
    monkeypatch.setenv("OPENAI_MODEL_CYPHER", "modelo-cypher")
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    llm = fabrica.obtener_llm("genera_cypher")

    assert llm.kwargs["model"] == "modelo-cypher"
    assert llm.kwargs["max_retries"] == 2
    assert llm.kwargs["timeout"] == 120


def test_rol_sin_variable_usa_modelo_global(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "modelo-global")
    monkeypatch.delenv("OPENAI_MODEL_ENTIDAD", raising=False)
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert fabrica.obtener_llm("resuelve_entidad").kwargs["model"] == "modelo-global"


def test_analista_curricular_usa_modelo_curricular_dedicado(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL_CURRICULAR", raising=False)
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert fabrica.obtener_llm("analista_curricular").kwargs["model"] == "gpt-5.6-luna"


def test_analista_curricular_permite_override_explicito(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL_CURRICULAR", "modelo-curricular-prueba")
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert (
        fabrica.obtener_llm("analista_curricular").kwargs["model"]
        == "modelo-curricular-prueba"
    )


def test_inspector_curricular_comparte_modelo_dedicado(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL_INSPECTOR_CURRICULAR", raising=False)
    monkeypatch.setenv("OPENAI_MODEL_CURRICULAR", "modelo-curricular-prueba")
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert fabrica.obtener_llm("inspector_curricular").kwargs["model"] == "modelo-curricular-prueba"


def test_roles_curriculares_residuales_usan_terra_por_defecto(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_MODEL_CURRICULAR_RESIDUAL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL", raising=False)
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert (
        fabrica.obtener_llm("analista_curricular_residual").kwargs["model"]
        == "gpt-5.6-terra"
    )
    assert (
        fabrica.obtener_llm("inspector_curricular_residual").kwargs["model"]
        == "gpt-5.6-terra"
    )


def test_inspector_curricular_residual_permite_override_independiente(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL_CURRICULAR_RESIDUAL", "terra-analista-prueba")
    monkeypatch.setenv(
        "OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL", "terra-inspector-prueba"
    )
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert (
        fabrica.obtener_llm("analista_curricular_residual").kwargs["model"]
        == "terra-analista-prueba"
    )
    assert (
        fabrica.obtener_llm("inspector_curricular_residual").kwargs["model"]
        == "terra-inspector-prueba"
    )


def test_sin_api_key_falla_claro(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        fabrica.obtener_llm("genera_cypher")
