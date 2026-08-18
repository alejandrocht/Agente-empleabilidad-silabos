"""Resolución unificada de perfiles curriculares por carrera y periodo."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import cast

from agente.normalizador.empleabilidad.catalogo import ruta_catalogos


def cargar_perfil_carrera(
    carrera: str,
    periodo: str,
    *,
    directorio_perfiles: Path | None = None,
    directorio_catalogos: Path | None = None,
) -> dict[str, object]:
    """Carga el perfil disponible o devuelve un perfil borrador explícito.

    El backend es la fuente preferente porque es el contexto que viaja al LLM.
    El catálogo externo se usa como respaldo para no duplicar perfiles durante
    la transición. La ausencia de perfil nunca se rellena con dominios
    inventados: queda declarada como ``BORRADOR`` y ``disponible=False``.
    """

    clave = clave_carrera(carrera)
    periodo_limpio = _periodo(periodo)
    candidatos = _rutas_perfil(
        clave,
        periodo_limpio,
        directorio_perfiles=directorio_perfiles,
        directorio_catalogos=directorio_catalogos,
    )
    for ruta, origen in candidatos:
        if not ruta.is_file():
            continue
        try:
            valor = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(valor, dict):
            continue
        perfil = dict(cast(dict[str, object], valor))
        perfil.setdefault("carrera", clave)
        perfil.setdefault("periodo", periodo_limpio)
        perfil.setdefault("estado", "BORRADOR")
        perfil.setdefault("revision", periodo_limpio)
        perfil["perfil_disponible"] = True
        perfil["origen_perfil"] = origen
        return perfil

    return {
        "carrera": clave,
        "periodo": periodo_limpio,
        "estado": "BORRADOR",
        "revision": "sin_perfil",
        "perfil_disponible": False,
        "origen_perfil": "pendiente_de_formalizacion",
        "reglas": [
            "Usar únicamente evidencia explícita del sílabo.",
            "No inventar competencias, habilidades ni herramientas.",
        ],
    }


def clave_carrera(valor: object) -> str:
    """Convierte el nombre visible de una carrera a la clave de catálogo."""

    normalizado = unicodedata.normalize("NFKD", str(valor or ""))
    normalizado = "".join(
        caracter for caracter in normalizado if not unicodedata.combining(caracter)
    )
    return re.sub(r"[^A-Za-z0-9]+", "_", normalizado).strip("_").upper()


def _periodo(valor: object) -> str:
    periodo = re.sub(r"[^0-9-]", "", str(valor or ""))
    if not periodo:
        raise ValueError("El periodo es obligatorio para cargar un perfil curricular.")
    return periodo


def _rutas_perfil(
    clave: str,
    periodo: str,
    *,
    directorio_perfiles: Path | None,
    directorio_catalogos: Path | None,
) -> tuple[tuple[Path, str], ...]:
    paquete = directorio_perfiles or Path(__file__).parent / "perfiles"
    catalogos = directorio_catalogos or ruta_catalogos()
    return (
        (paquete / clave / f"{periodo}.json", "backend_perfil"),
        (
            catalogos / "carreras" / clave / periodo / "perfil.json",
            "catalogo_carrera",
        ),
    )
