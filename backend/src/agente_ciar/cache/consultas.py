"""Caché RAM de Cypher, filas y respuesta final con vencimiento configurable."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from agente_ciar.config.settings import entero

_TTL = entero("CACHE_TTL_SEGUNDOS", 600)
_MAX_ENTRADAS = entero("CACHE_MAX_ENTRADAS", 500)
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = RLock()


def _clave(pregunta: str, entidades: list[dict[str, Any]]) -> str:
    """Genera una clave estable a partir del texto normalizado y los ids de entidades."""
    texto = " ".join(pregunta.lower().split())
    slots = sorted(
        ({"label": item.get("label", ""), "id": item.get("id", "")} for item in entidades),
        key=lambda item: (str(item["label"]), str(item["id"])),
    )
    contenido = json.dumps({"pregunta": texto, "entidades": slots}, ensure_ascii=False)
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()[:16]


def _depurar_vencidas() -> None:
    """Elimina entradas vencidas; debe invocarse mientras ``_LOCK`` está adquirido."""
    ahora = datetime.now(UTC)
    vencidas = [
        clave
        for clave, entrada in _CACHE.items()
        if (ahora - datetime.fromisoformat(entrada["creado_en"])).total_seconds() >= _TTL
    ]
    for clave in vencidas:
        del _CACHE[clave]


def _limitar_tamano() -> None:
    """Conserva las entradas más recientes para acotar la memoria del proceso."""
    exceso = len(_CACHE) - _MAX_ENTRADAS
    if exceso <= 0:
        return
    antiguas = sorted(_CACHE, key=lambda clave: _CACHE[clave]["creado_en"])[:exceso]
    for clave in antiguas:
        del _CACHE[clave]


def buscar(pregunta: str, entidades: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Entrega una copia de la entrada vigente o elimina una entrada que ya venció."""
    clave = _clave(pregunta, entidades)
    with _LOCK:
        _depurar_vencidas()
        entrada = _CACHE.get(clave)
        if not entrada:
            return None
        return deepcopy({k: v for k, v in entrada.items() if k != "creado_en"})


def guardar(
    pregunta: str,
    entidades: list[dict[str, Any]],
    cypher: str,
    filas: list[dict[str, Any]],
    respuesta: str,
) -> None:
    """Guarda el resultado completo para evitar LLM y Neo4j en una repetición exacta."""
    with _LOCK:
        _depurar_vencidas()
        _CACHE[_clave(pregunta, entidades)] = {
            "cypher": cypher,
            "filas": deepcopy(filas),
            "respuesta": respuesta,
            "creado_en": datetime.now(UTC).isoformat(),
        }
        _limitar_tamano()


def limpiar() -> None:
    """Vacía la caché; esta operación se reserva para pruebas y reinicios locales."""
    with _LOCK:
        _CACHE.clear()
