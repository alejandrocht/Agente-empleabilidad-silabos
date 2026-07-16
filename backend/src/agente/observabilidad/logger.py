"""Logger JSON centralizado para auditar cada nodo y cada turno.

LangSmith se activa mediante ``LANGSMITH_TRACING=true``. LangChain y ChatOpenAI leen esas
variables automáticamente, por lo que las llamadas LLM no necesitan envoltorios propios.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Se instala un único handler para evitar duplicar eventos al recargar la API en desarrollo.
_logger = logging.getLogger("agente")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


def log_paso(
    nodo: str,
    evento: str,
    id_sesion: str = "",
    data: dict[str, Any] | None = None,
    nivel: str = "info",
) -> None:
    """Registra un evento estructurado sin incluir secretos ni resultados completos."""
    entrada = {
        "ts": datetime.now(UTC).isoformat(),
        "sesion": id_sesion or "desconocida",
        "nodo": nodo,
        "evento": evento,
        "data": data or {},
    }
    mensaje = json.dumps(entrada, ensure_ascii=False, default=str)

    # Solo se aceptan los tres niveles usados por el flujo; cualquier otro cae a ``info``.
    escritor = {"error": _logger.error, "warning": _logger.warning}.get(nivel, _logger.info)
    escritor(mensaje)


def log_inicio_turno(id_sesion: str, pregunta: str) -> None:
    """Marca el inicio del turno limitando la pregunta para no inflar ni filtrar datos."""
    log_paso("turno", "inicio", id_sesion, {"pregunta": pregunta[:120]})


def log_fin_turno(id_sesion: str, respuesta: str, nodos: list[str]) -> None:
    """Marca el cierre del turno con métricas pequeñas y los nodos visitados."""
    log_paso(
        "turno",
        "fin",
        id_sesion,
        {"respuesta_chars": len(respuesta), "nodos": nodos},
    )
