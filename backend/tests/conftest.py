"""Configuración común: paquete ``src`` importable y observabilidad remota apagada."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Las pruebas nunca deben enviar trazas reales ni depender de una instalación editable previa.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["INSPECTOR_LLM"] = "false"
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


@pytest.fixture(autouse=True)
def limpiar_estado_ram() -> None:
    """Aísla caché y memorias efímeras entre casos de prueba."""
    from agente_ciar.cache.consultas import limpiar as limpiar_cache
    from agente_ciar.memoria.bloques import limpiar as limpiar_bloques
    from agente_ciar.memoria.conversacional import limpiar as limpiar_conversacional

    limpiar_cache()
    limpiar_bloques()
    limpiar_conversacional()
    yield
    limpiar_cache()
    limpiar_bloques()
    limpiar_conversacional()
