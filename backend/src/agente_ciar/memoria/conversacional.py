"""Estado vivo de entidades activas por sesión, almacenado en RAM con TTL."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from agente_ciar.config.settings import entero

# La memoria es deliberadamente efímera; al vencer evita reutilizar referencias antiguas.
_TTL = entero("MEMORIA_TTL_SEGUNDOS", 1800)
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = RLock()
_SESION_DEFAULT = "__default__"


def _ahora() -> datetime:
    """Entrega una fecha UTC consciente de zona horaria para comparar el TTL."""
    return datetime.now(UTC)


def _clave(id_sesion: str | None) -> str:
    """Normaliza ids vacíos para que los accesos de consola sigan siendo deterministas."""
    return (id_sesion or "").strip() or _SESION_DEFAULT


def _nueva() -> dict[str, Any]:
    """Crea una memoria sin entidades y con una marca temporal vigente."""
    return {"entidades_activas": {}, "tema_actual": "", "updated_at": _ahora().isoformat()}


def obtener(id_sesion: str | None) -> dict[str, Any]:
    """Devuelve una copia del estado vivo y lo reinicia primero si ya venció."""
    clave = _clave(id_sesion)
    with _LOCK:
        memoria = _CACHE.setdefault(clave, _nueva())
        antiguedad = (_ahora() - datetime.fromisoformat(memoria["updated_at"])).total_seconds()
        if antiguedad > _TTL:
            memoria = _CACHE[clave] = _nueva()
        return deepcopy(memoria)


def actualizar_entidades(id_sesion: str | None, entidades: list[dict[str, Any]]) -> None:
    """Sobrescribe el slot del label con la entidad resuelta más reciente."""
    if not entidades:
        return
    clave = _clave(id_sesion)
    with _LOCK:
        memoria = _CACHE.setdefault(clave, _nueva())
        for entidad in entidades:
            label = str(entidad.get("label", "")).strip()
            if not label:
                continue
            memoria["entidades_activas"][label] = {
                "label": label,
                "texto": entidad.get("texto"),
                "nombre": entidad.get("nombre"),
                "id": entidad.get("id"),
            }
        memoria["updated_at"] = _ahora().isoformat()


def entidades_activas(id_sesion: str | None) -> list[dict[str, Any]]:
    """Expone los slots activos como lista lista para el estado de LangGraph."""
    memoria = obtener(id_sesion)
    return list(memoria["entidades_activas"].values())


def formatear(id_sesion: str | None) -> str:
    """Forma un contexto breve con entidades vivas y resúmenes históricos existentes."""
    memoria = obtener(id_sesion)
    lineas: list[str] = []
    if memoria["entidades_activas"]:
        lineas.append("Entidades activas de la sesión:")
        for label, entidad in memoria["entidades_activas"].items():
            nombre = entidad.get("nombre") or entidad.get("texto") or ""
            identificador = f" ({entidad.get('id')})" if entidad.get("id") else ""
            lineas.append(f"- {label}: {nombre}{identificador}")

    # El import local mantiene separados el estado vivo y la memoria resumida por bloques.
    from agente_ciar.memoria.bloques import obtener_bloques

    bloques = obtener_bloques(id_sesion)
    if bloques:
        lineas.append("Resumen de bloques anteriores:")
        lineas.extend(f"- {bloque}" for bloque in bloques[-4:])
    return "\n".join(lineas) if lineas else "(sin memoria previa de esta sesión)"


def limpiar(id_sesion: str | None = None) -> None:
    """Limpia una sesión o toda la memoria; se usa en pruebas y mantenimiento local."""
    with _LOCK:
        if id_sesion is None:
            _CACHE.clear()
        else:
            _CACHE.pop(_clave(id_sesion), None)
