"""Memoria conversacional en cache de sesion.

La memoria vive solo en RAM: se pierde al cerrar el proceso y se separa por id_sesion.
Combina una ventana corta de turnos recientes con un resumen compacto de turnos viejos.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any, TypedDict


MAX_TURNOS_RECIENTES = 4
MAX_BLOQUES_RESUMEN = 8
MAX_ENTIDADES_RECIENTES = 12
MAX_PREGUNTA_CHARS = 240
MAX_RESPUESTA_CHARS = 360
MAX_BLOQUE_RESUMEN_CHARS = 420
ID_SESION_DEFAULT = "__default__"


class TurnoMemoria(TypedDict, total=False):
    pregunta: str
    respuesta: str
    entidades: list[dict[str, Any]]
    cypher: str
    error: str | None


class MemoriaSesion(TypedDict):
    resumen: list[str]
    turnos_recientes: list[TurnoMemoria]
    entidades_recientes: list[dict[str, Any]]
    updated_at: str


_CACHE: dict[str, MemoriaSesion] = {}
_LOCK = RLock()


def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalizar_id(id_sesion: str | None) -> str:
    id_limpio = (id_sesion or "").strip()
    return id_limpio or ID_SESION_DEFAULT


def _nueva_memoria() -> MemoriaSesion:
    return {
        "resumen": [],
        "turnos_recientes": [],
        "entidades_recientes": [],
        "updated_at": _ahora_iso(),
    }


def _recortar(texto: Any, max_chars: int) -> str:
    limpio = " ".join(str(texto or "").split())
    if len(limpio) <= max_chars:
        return limpio
    return limpio[: max_chars - 3].rstrip() + "..."


def _limpiar_entidad(entidad: dict[str, Any]) -> dict[str, str]:
    limpia: dict[str, str] = {}
    for clave in ("texto", "label", "nombre", "id"):
        valor = _recortar(entidad.get(clave), 160)
        if valor:
            limpia[clave] = valor
    return limpia


def _clave_entidad(entidad: dict[str, str]) -> tuple[str, str]:
    label = entidad.get("label", "")
    valor = entidad.get("id") or entidad.get("nombre") or entidad.get("texto", "")
    return (label, valor.lower())


def _entidades_a_texto(entidades: list[dict[str, Any]] | None) -> str:
    if not entidades:
        return "sin entidades"

    partes = []
    for entidad in entidades:
        label = entidad.get("label") or "Entidad"
        nombre = entidad.get("nombre") or entidad.get("texto") or ""
        entidad_id = entidad.get("id")
        if entidad_id:
            partes.append(f"{label}={nombre} ({entidad_id})")
        elif nombre:
            partes.append(f"{label}={nombre}")
    return "; ".join(partes) if partes else "sin entidades"


def _normalizar_turno(turno: TurnoMemoria) -> TurnoMemoria:
    limpio: TurnoMemoria = {
        "pregunta": _recortar(turno.get("pregunta"), MAX_PREGUNTA_CHARS),
        "respuesta": _recortar(turno.get("respuesta"), MAX_RESPUESTA_CHARS),
    }

    entidades = [
        entidad_limpia
        for entidad in turno.get("entidades", [])
        if (entidad_limpia := _limpiar_entidad(entidad))
    ]
    if entidades:
        limpio["entidades"] = entidades

    cypher = _recortar(turno.get("cypher"), 240)
    if cypher:
        limpio["cypher"] = cypher

    error = _recortar(turno.get("error"), 240)
    if error:
        limpio["error"] = error

    return limpio


def _resumir_turno(turno: TurnoMemoria) -> str:
    pregunta = _recortar(turno.get("pregunta"), 120)
    respuesta = _recortar(turno.get("respuesta"), 180)
    entidades = _entidades_a_texto(turno.get("entidades", []))
    return _recortar(
        f"P: {pregunta} | R: {respuesta} | Entidades: {entidades}",
        MAX_BLOQUE_RESUMEN_CHARS,
    )


def _compactar_resumen(resumen: list[str]) -> list[str]:
    if len(resumen) <= MAX_BLOQUES_RESUMEN:
        return resumen

    cantidad_reciente = MAX_BLOQUES_RESUMEN - 1
    antiguos = resumen[:-cantidad_reciente]
    recientes = resumen[-cantidad_reciente:]
    bloque_antiguo = _recortar(
        "Contexto anterior compactado: " + " / ".join(antiguos),
        MAX_BLOQUE_RESUMEN_CHARS,
    )
    return [bloque_antiguo, *recientes]


def _actualizar_entidades_recientes(
    entidades_actuales: list[dict[str, str]],
    nuevas_entidades: list[dict[str, Any]] | None,
    pregunta: str,
) -> list[dict[str, str]]:
    entidades = list(entidades_actuales)
    for entidad in nuevas_entidades or []:
        limpia = _limpiar_entidad(entidad)
        if not limpia:
            continue
        limpia["origen_pregunta"] = _recortar(pregunta, 120)
        clave = _clave_entidad(limpia)
        entidades = [existente for existente in entidades if _clave_entidad(existente) != clave]
        entidades.append(limpia)
    return entidades[-MAX_ENTIDADES_RECIENTES:]


def obtener_memoria(id_sesion: str | None) -> MemoriaSesion:
    """Devuelve una copia de la memoria de una sesion."""
    clave = _normalizar_id(id_sesion)
    with _LOCK:
        memoria = _CACHE.setdefault(clave, _nueva_memoria())
        return deepcopy(memoria)


def actualizar_memoria(id_sesion: str | None, turno: TurnoMemoria) -> MemoriaSesion:
    """Agrega un turno a la memoria y mantiene sus limites de tamano."""
    clave = _normalizar_id(id_sesion)
    turno_limpio = _normalizar_turno(turno)

    with _LOCK:
        memoria = _CACHE.setdefault(clave, _nueva_memoria())
        pregunta = turno_limpio.get("pregunta", "")

        memoria["turnos_recientes"].append(turno_limpio)
        memoria["entidades_recientes"] = _actualizar_entidades_recientes(
            memoria["entidades_recientes"],
            turno_limpio.get("entidades", []),
            pregunta,
        )

        if len(memoria["turnos_recientes"]) > MAX_TURNOS_RECIENTES:
            antiguos = memoria["turnos_recientes"][:-MAX_TURNOS_RECIENTES]
            memoria["resumen"].extend(_resumir_turno(turno_antiguo) for turno_antiguo in antiguos)
            memoria["resumen"] = _compactar_resumen(memoria["resumen"])
            memoria["turnos_recientes"] = memoria["turnos_recientes"][-MAX_TURNOS_RECIENTES:]

        memoria["updated_at"] = _ahora_iso()
        return deepcopy(memoria)


def formatear_memoria(memoria: MemoriaSesion | None) -> str:
    """Convierte la memoria en texto breve para inyectarlo en prompts."""
    if not memoria:
        return "(sin memoria previa de esta sesion)"

    partes: list[str] = []

    resumen = memoria.get("resumen", [])
    if resumen:
        partes.append("Resumen compacto de turnos anteriores:")
        partes.extend(f"- {bloque}" for bloque in resumen)

    entidades = memoria.get("entidades_recientes", [])
    if entidades:
        partes.append("Entidades recientes de la sesion:")
        for entidad in entidades:
            label = entidad.get("label") or "Entidad"
            nombre = entidad.get("nombre") or entidad.get("texto") or ""
            entidad_id = entidad.get("id")
            origen = entidad.get("origen_pregunta")
            detalle_id = f" ({entidad_id})" if entidad_id else ""
            detalle_origen = f"; origen: {origen}" if origen else ""
            partes.append(f"- {label}: {nombre}{detalle_id}{detalle_origen}")

    turnos = memoria.get("turnos_recientes", [])
    if turnos:
        partes.append("Ultimos turnos completos:")
        for indice, turno in enumerate(turnos, start=1):
            partes.append(
                f"{indice}. Usuario: {turno.get('pregunta', '')}\n"
                f"   Agente: {turno.get('respuesta', '')}"
            )

    return "\n".join(partes) if partes else "(sin memoria previa de esta sesion)"


def limpiar_memoria(id_sesion: str | None = None) -> None:
    """Limpia una sesion concreta o toda la cache. Util para pruebas."""
    with _LOCK:
        if id_sesion is None:
            _CACHE.clear()
            return
        _CACHE.pop(_normalizar_id(id_sesion), None)
