"""Configuración común para pruebas deterministas y sin llamadas externas."""

from __future__ import annotations

import os
from pathlib import Path

# Las pruebas del normalizador ejercitan el fallback determinista. Evitar que
# una variable del entorno de desarrollo active llamadas LLM o trazas remotas
# hace que el resultado sea reproducible y no dependa de credenciales.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["NORMALIZADOR_CURRICULAR_LLM"] = "false"
os.environ["NORMALIZADOR_CURRICULAR_INSPECTOR"] = "false"
os.environ["NORMALIZADOR_CATALOGOS_DIR"] = str(
    Path(__file__).resolve().parent / "fixtures" / "catalogos"
)
