"""Configuración centralizada del backend.

El archivo ``.env`` se lee desde la raíz de ``backend``. ``setdefault`` conserva cualquier
valor que el proceso haya recibido desde el sistema o desde el entorno de despliegue.
"""

from __future__ import annotations

import os
from pathlib import Path

# Desde ``src/agente/config`` se suben tres niveles hasta la raíz de ``backend``.
BASE_DIR = Path(__file__).resolve().parents[3]


def cargar_entorno() -> None:
    """Carga las variables definidas en ``backend/.env`` cuando el archivo existe."""
    ruta_env = BASE_DIR / ".env"
    if not ruta_env.exists():
        return

    # Se ignoran comentarios, líneas vacías y entradas mal formadas.
    for linea in ruta_env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


# La carga ocurre al importar settings para que LangGraph, la API y la consola compartan fuente.
cargar_entorno()


def texto(clave: str, default: str = "") -> str:
    """Lee texto del entorno ya cargado y elimina espacios externos."""
    return os.getenv(clave, default).strip()


def entero(clave: str, default: int) -> int:
    """Lee un entero de configuración."""
    return int(texto(clave, str(default)))


def decimal(clave: str, default: float) -> float:
    """Lee un número decimal de configuración."""
    return float(texto(clave, str(default)))


def booleano(clave: str, default: bool = False) -> bool:
    """Lee booleanos habituales sin dispersar conversiones entre módulos."""
    valor = texto(clave, str(default)).lower()
    return valor in {"1", "true", "yes", "on", "si", "sí"}
