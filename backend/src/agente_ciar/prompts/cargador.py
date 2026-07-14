"""Carga los prompts Markdown incluidos dentro del paquete instalable."""

from __future__ import annotations

from pathlib import Path

# Los prompts viven junto al cargador y setuptools los incluye como datos del paquete.
CARPETA_PROMPTS = Path(__file__).resolve().parent


def cargar_prompt(nombre: str) -> str:
    """Lee ``prompts/<nombre>.md`` y falla con una ruta clara si no existe."""
    ruta = CARPETA_PROMPTS / f"{nombre}.md"
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el prompt: {ruta}")
    return ruta.read_text(encoding="utf-8")
