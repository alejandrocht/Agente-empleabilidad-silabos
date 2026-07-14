"""Pruebas de la selección OpenAI por rol y sus fallos claros."""

from __future__ import annotations

import pytest

from agente_ciar.llm import fabrica


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
    assert llm.kwargs["max_retries"] == 3


def test_rol_sin_variable_usa_modelo_global(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "modelo-global")
    monkeypatch.delenv("OPENAI_MODEL_ENTIDAD", raising=False)
    monkeypatch.setattr(fabrica, "ChatOpenAI", ChatOpenAIFalso)

    assert fabrica.obtener_llm("resuelve_entidad").kwargs["model"] == "modelo-global"


def test_sin_api_key_falla_claro(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        fabrica.obtener_llm("genera_cypher")
