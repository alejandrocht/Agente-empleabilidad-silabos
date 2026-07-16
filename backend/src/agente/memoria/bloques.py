"""Resumen LLM de la conversación cada doce turnos completos."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any

from agente.config.settings import entero
from agente.llm.fabrica import obtener_llm
from agente.observabilidad.logger import log_paso
from agente.prompts.cargador import cargar_prompt

_CADA = entero("MEMORIA_BLOQUE_CADA", 12)
_TTL = entero("MEMORIA_TTL_SEGUNDOS", 1800)
_CACHE: dict[str, dict[str, Any]] = {}
_LOCK = RLock()
_SESION_DEFAULT = "__default__"


def _clave(id_sesion: str | None) -> str:
    """Normaliza el id para aislar las conversaciones en el diccionario de RAM."""
    return (id_sesion or "").strip() or _SESION_DEFAULT


def _nuevo_estado() -> dict[str, Any]:
    """Crea el acumulador efímero de una sesión."""
    return {
        "contador": 0,
        "pendientes": [],
        "bloques": [],
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _estado_vigente(clave: str) -> dict[str, Any]:
    """Obtiene el estado y lo reemplaza si superó el TTL conversacional."""
    estado = _CACHE.setdefault(clave, _nuevo_estado())
    edad = (datetime.now(UTC) - datetime.fromisoformat(estado["updated_at"])).total_seconds()
    if edad > _TTL:
        estado = _CACHE[clave] = _nuevo_estado()
    return estado


def _resumir(turnos: list[str]) -> str:
    """Solicita a OpenAI un resumen factual y corto del bloque acumulado."""
    prompt = cargar_prompt("resumen_memoria").replace("{turnos}", "\n".join(turnos))
    return str(obtener_llm("resumen_memoria").invoke(prompt).content).strip()


def registrar_mensaje(id_sesion: str | None, pregunta: str, respuesta: str) -> None:
    """Registra un turno y resume fuera del lock cuando alcanza el tamaño configurado."""
    clave = _clave(id_sesion)
    pendientes_resumen: list[str] = []
    with _LOCK:
        estado = _estado_vigente(clave)
        estado["contador"] += 1
        estado["pendientes"].append(f"P: {pregunta} | R: {respuesta}")
        estado["updated_at"] = datetime.now(UTC).isoformat()
        if estado["contador"] >= _CADA:
            pendientes_resumen = list(estado["pendientes"])
            estado["pendientes"] = []
            estado["contador"] = 0

    # La llamada remota no bloquea actualizaciones de memoria de otras sesiones.
    if pendientes_resumen:
        try:
            resumen = _resumir(pendientes_resumen)
        except Exception as exc:
            # Un fallo de resumen no invalida una respuesta que ya fue obtenida correctamente.
            log_paso(
                "resumen_memoria",
                "error",
                clave,
                {"error": str(exc)[:200]},
                nivel="warning",
            )
            with _LOCK:
                estado = _estado_vigente(clave)
                estado["pendientes"] = pendientes_resumen + estado["pendientes"]
                estado["contador"] = len(estado["pendientes"])
                estado["updated_at"] = datetime.now(UTC).isoformat()
            return
        with _LOCK:
            estado = _estado_vigente(clave)
            estado["bloques"].append(resumen)
            estado["updated_at"] = datetime.now(UTC).isoformat()
        log_paso("resumen_memoria", "bloque_creado", clave, {"turnos": len(pendientes_resumen)})


def obtener_bloques(id_sesion: str | None) -> list[str]:
    """Devuelve una copia de los resúmenes ya consolidados para la sesión."""
    with _LOCK:
        estado = _estado_vigente(_clave(id_sesion))
        return deepcopy(estado["bloques"])


def limpiar(id_sesion: str | None = None) -> None:
    """Limpia una sesión o toda la memoria por bloques para aislar pruebas."""
    with _LOCK:
        if id_sesion is None:
            _CACHE.clear()
        else:
            _CACHE.pop(_clave(id_sesion), None)
