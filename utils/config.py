"""
Carga de configuracion (.env) en un solo lugar.

La idea es tener UNA sola funcion (cargar_entorno) que lea el archivo .env y meta
sus valores en las variables de entorno del sistema. Asi cualquier otro archivo
puede leer la config con os.getenv(...) sin preocuparse de donde salio.
"""
from __future__ import annotations

# os nos da acceso a las variables de entorno (os.environ / os.getenv).
import os
# Path nos permite construir rutas de archivos de forma segura en cualquier sistema.
from pathlib import Path

# Carpeta raiz del proyecto = la carpeta que contiene a "utils" (subimos un nivel).
# __file__ es la ruta de ESTE archivo; .parent sube a "utils"; .parent otra vez a la raiz.
BASE_DIR = Path(__file__).resolve().parent.parent


def cargar_entorno() -> None:
    """Lee el archivo .env (si existe) y copia sus valores a las variables de entorno."""
    # Ruta esperada del .env: en la raiz del proyecto.
    ruta_env = BASE_DIR / ".env"

    # Si no hay .env, no hacemos nada (se usaran los valores por defecto del codigo).
    if not ruta_env.exists():
        return

    # Recorremos el archivo linea por linea.
    for linea_cruda in ruta_env.read_text(encoding="utf-8").splitlines():
        # Quitamos espacios al inicio y al final.
        linea = linea_cruda.strip()

        # Ignoramos lineas vacias, comentarios (#) y las que no tengan un "=".
        if not linea or linea.startswith("#") or "=" not in linea:
            continue

        # Partimos solo en el PRIMER "=" (por si el valor tambien tiene "=").
        clave, valor = linea.split("=", 1)

        # Limpiamos la clave y el valor (espacios y comillas alrededor del valor).
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")

        # setdefault NO pisa una variable que ya este definida en el entorno real;
        # esto permite, por ejemplo, sobreescribir desde la terminal si hace falta.
        os.environ.setdefault(clave, valor)
