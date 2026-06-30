"""
Helper para cargar prompts desde la carpeta /prompts.

Cada nodo que usa LLM tiene su prompt guardado en un archivo de texto (.md) aparte.
Asi el texto del prompt se puede editar sin tocar el codigo Python.
"""
from __future__ import annotations

from pathlib import Path

# Carpeta raiz del proyecto (subimos de "utils" a la raiz) y de ahi a "prompts".
BASE_DIR = Path(__file__).resolve().parent.parent
CARPETA_PROMPTS = BASE_DIR / "prompts"


def cargar_prompt(nombre: str) -> str:
    """Lee y devuelve el contenido del archivo prompts/<nombre>.md como texto."""
    # Construimos la ruta del archivo del prompt, ej: prompts/genera_cypher.md
    ruta = CARPETA_PROMPTS / f"{nombre}.md"

    # Si el archivo no existe, avisamos con un error claro (mejor que fallar raro despues).
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontro el prompt: {ruta}")

    # Devolvemos todo el texto del archivo.
    return ruta.read_text(encoding="utf-8")
