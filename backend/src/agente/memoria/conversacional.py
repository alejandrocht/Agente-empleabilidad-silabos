"""Entidades activas e historial reciente por sesión, almacenados en RAM con TTL."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any, cast

from agente.config.settings import entero

# La memoria es deliberadamente efímera; al vencer evita reutilizar referencias antiguas.
_TTL = entero("MEMORIA_TTL_SEGUNDOS", 1800)
_LIMITE_HISTORIAL = entero("MEMORIA_HISTORIAL_ENTIDADES", 8)
_CACHE: dict[str, dict[str, Any]] = {}
#protege el cache de tener accesos simultaneos y corrupcion de datos
_LOCK = RLock()
#identificador para pruebas
_SESION_DEFAULT = "__default__"

#obtiene la fecha de ahora para poder luego calcular la vigencia de memoria y el TTL
def _ahora() -> datetime:
    """Entrega una fecha UTC consciente de zona horaria para comparar el TTL."""
    return datetime.now(UTC)

#obtiene el sesion id para poder identificar la memoria de cada usuario
def _clave(id_sesion: str | None) -> str:
    """Normaliza ids vacíos para que los accesos de consola sigan siendo deterministas."""
    return (id_sesion or "").strip() or _SESION_DEFAULT


def _nueva() -> dict[str, Any]:
    """Crea una memoria sin entidades y con una marca temporal vigente."""
    return {
        "entidades_activas": {},
        "historial_entidades": {},
        "tema_actual": "",
        "updated_at": _ahora().isoformat(),
    }


def _vigente(clave: str) -> dict[str, Any]:
    """Obtiene la sesión, migra su forma anterior y aplica el TTL bajo el lock."""
    memoria = _CACHE.setdefault(clave, _nueva())
    memoria.setdefault("entidades_activas", {})
    memoria.setdefault("historial_entidades", {})
    antiguedad = (_ahora() - datetime.fromisoformat(memoria["updated_at"])).total_seconds()
    if antiguedad > _TTL:
        memoria = _CACHE[clave] = _nueva()
    return memoria


def _limpiar_entidad(entidad: dict[str, Any], label: str) -> dict[str, Any]:
    """Conserva solo los campos conversacionales estables de una entidad resuelta."""
    return {
        "label": label,
        "texto": entidad.get("texto"),
        "nombre": entidad.get("nombre"),
        "id": entidad.get("id"),
    }


def _firma(entidad: dict[str, Any]) -> tuple[str, str]:
    """Identifica entidades repetidas por id y, como respaldo, por nombre o texto."""
    identificador = entidad.get("id")
    if identificador not in (None, ""):
        return "id", str(identificador)
    nombre = entidad.get("nombre") or entidad.get("texto") or ""
    return "nombre", str(nombre).strip().casefold()


def obtener(id_sesion: str | None) -> dict[str, Any]:
    """Devuelve una copia del estado vivo y lo reinicia primero si ya venció."""
    clave = _clave(id_sesion)
    with _LOCK:
        return deepcopy(_vigente(clave))


def actualizar_entidades(id_sesion: str | None, entidades: list[dict[str, Any]]) -> None:
    """Activa entidades y registra cambios reales en el historial de cada label."""
    if not entidades:
        return
    clave = _clave(id_sesion)
    with _LOCK:
        memoria = _vigente(clave)
        for entidad in entidades:
            label = str(entidad.get("label", "")).strip()
            if not label:
                continue
            limpia = _limpiar_entidad(entidad, label)
            memoria["entidades_activas"][label] = limpia
            historial = memoria["historial_entidades"].setdefault(label, [])
            if historial and _firma(historial[-1]) == _firma(limpia):
                historial[-1] = limpia
            else:
                historial.append(limpia)
                limite = max(1, _LIMITE_HISTORIAL)
                del historial[:-limite]
        memoria["updated_at"] = _ahora().isoformat()


def entidades_activas(id_sesion: str | None) -> list[dict[str, Any]]:
    """Expone los slots activos como lista lista para el estado de LangGraph."""
    memoria = obtener(id_sesion)
    return list(memoria["entidades_activas"].values())


def historial_entidades(id_sesion: str | None) -> dict[str, list[dict[str, Any]]]:
    """Expone el historial cronológico reciente agrupado por label."""
    memoria = obtener(id_sesion)
    return cast(dict[str, list[dict[str, Any]]], memoria["historial_entidades"])


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

    historiales = memoria["historial_entidades"]
    if any(len(entidades) > 1 for entidades in historiales.values()):
        lineas.append("Historial reciente de entidades (de anterior a activa):")
        for label, entidades in historiales.items():
            if len(entidades) < 2:
                continue
            nombres = [
                str(item.get("nombre") or item.get("texto") or item.get("id"))
                for item in entidades
            ]
            lineas.append(f"- {label}: {' -> '.join(nombres)}")

    # El import local mantiene separados el estado vivo y la memoria resumida por bloques.
    from agente.memoria.bloques import obtener_bloques

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
