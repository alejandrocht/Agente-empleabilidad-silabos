"""Configuración común para pruebas deterministas y sin llamadas externas."""

from __future__ import annotations

import os
from pathlib import Path

# Las pruebas del normalizador ejercitan el fallback determinista. Evitar que
# una variable del entorno de desarrollo active llamadas LLM o trazas remotas
# hace que el resultado sea reproducible y no dependa de credenciales.
os.environ["LANGSMITH_TRACING"] = "false"
# Tests assert the complete structured event stream; the local development
# server may use ``CIAR_LOG_SCOPE=nodes`` to show only graph boundaries.
os.environ["CIAR_LOG_SCOPE"] = "all"
os.environ["CIAR_NODE_LOG_VALUES"] = "0"
os.environ["CIAR_LOG_FORMAT"] = "json"
os.environ["NORMALIZADOR_CURRICULAR_LLM"] = "false"
os.environ["NORMALIZADOR_CURRICULAR_INSPECTOR"] = "false"
os.environ["NORMALIZADOR_CATALOGOS_DIR"] = str(
    Path(__file__).resolve().parent / "fixtures" / "catalogos"
)
