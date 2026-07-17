"""Eventos de negocio legibles y trazas técnicas seguras para el backend CIAR.

Los eventos se conservan internamente como JSON para que puedan enviarse a un colector,
pero en desarrollo se presentan como ``[campo]: valor``. Las funciones de bajo nivel se
perfilan solo con ``LOG_NIVEL=DEBUG``; INFO queda reservado para decisiones y cambios de estado.
"""

from __future__ import annotations

import contextvars
import hashlib
import inspect
import json
import logging
import sys
import threading
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from agente.config.settings import booleano, entero, texto

NOMBRE_LOGGER = "agente"
_MODULO_LOGGER = __name__
_MAX_CHARS = entero("LOG_MAX_CHARS_CAMPO", 800)
_MOSTRAR_SESION_COMPLETA = booleano("LOG_SESION_COMPLETA", False)
_CLAVES_SENSIBLES = (
    "api_key",
    "authorization",
    "contrasena",
    "contraseña",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)
_sesion_actual: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agente_sesion_log", default="desconocida"
)


def _valor_legible(valor: Any) -> str:
    if isinstance(valor, str):
        return valor
    return json.dumps(valor, ensure_ascii=False, default=str, separators=(",", ":"))


class FormateadorLegible(logging.Formatter):
    """Presenta cada atributo con el patrón explícito ``[campo]: valor``."""

    def format(self, record: logging.LogRecord) -> str:
        mensaje = record.getMessage()
        try:
            entrada = json.loads(mensaje)
        except (json.JSONDecodeError, TypeError):
            return f"[nivel]: {record.levelname} [mensaje]: {mensaje}"
        if not isinstance(entrada, dict):
            return f"[nivel]: {record.levelname} [mensaje]: {mensaje}"

        campos: list[tuple[str, Any]] = [
            ("nivel", record.levelname),
            ("sesion", entrada.get("sesion", "desconocida")),
            ("evento", entrada.get("evento", "evento.desconocido")),
            ("funcion", entrada.get("funcion", "desconocida")),
        ]
        data = entrada.get("data", {})
        if isinstance(data, dict):
            campos.extend((str(clave), valor) for clave, valor in data.items())
        elif data not in ({}, None):
            campos.append(("detalle", data))

        detalle = " ".join(f"[{clave}]: {_valor_legible(valor)}" for clave, valor in campos)
        return f"{self._hora(str(entrada.get('ts', '')))} {detalle}"

    @staticmethod
    def _hora(valor: str) -> str:
        try:
            fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return "--:--:--.---"
        return fecha.astimezone(UTC).strftime("%H:%M:%S.%f")[:-3]


def _crear_formateador() -> logging.Formatter:
    if texto("LOG_FORMATO", "legible").lower() == "json":
        return logging.Formatter("%(message)s")
    return FormateadorLegible()


def _crear_logger() -> logging.Logger:
    logger = logging.getLogger(NOMBRE_LOGGER)
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler(sys.stdout))
    for handler in logger.handlers:
        handler.setFormatter(_crear_formateador())
    logger.setLevel(getattr(logging, texto("LOG_NIVEL", "INFO").upper(), logging.INFO))
    return logger


_logger = _crear_logger()


def _funcion_llamadora() -> str:
    frame = inspect.currentframe()
    if frame is None:
        return "desconocida"
    frame = frame.f_back
    while frame is not None:
        modulo = str(frame.f_globals.get("__name__", ""))
        if modulo != _MODULO_LOGGER:
            return f"{modulo}.{frame.f_code.co_qualname}"
        frame = frame.f_back
    return "desconocida"


def _sesion_para_log(id_sesion: str) -> str:
    sesion = id_sesion.strip() or "desconocida"
    if sesion == "desconocida" or _MOSTRAR_SESION_COMPLETA:
        return sesion
    digest = hashlib.sha256(sesion.encode("utf-8")).hexdigest()[:12]
    return f"ses-{digest}"


def _es_clave_sensible(clave: str) -> bool:
    normalizada = clave.casefold()
    return any(fragmento in normalizada for fragmento in _CLAVES_SENSIBLES)


def _sanear(valor: Any, clave: str = "", profundidad: int = 0) -> Any:
    """Evita secretos, inyección de líneas y payloads sin límite en cualquier evento."""
    if _es_clave_sensible(clave):
        return "[REDACTADO]"
    if profundidad >= 8:
        return "[PROFUNDIDAD_LIMITADA]"
    if isinstance(valor, dict):
        return {
            str(k): _sanear(v, str(k), profundidad + 1)
            for k, v in list(valor.items())[:50]
        }
    if isinstance(valor, (list, tuple, set)):
        return [_sanear(item, clave, profundidad + 1) for item in list(valor)[:50]]
    if isinstance(valor, str):
        una_linea = valor.replace("\r", "\\r").replace("\n", "\\n")
        return una_linea if len(una_linea) <= _MAX_CHARS else una_linea[:_MAX_CHARS] + "…"
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    return _sanear(str(valor), clave, profundidad)


def log_paso(
    nodo: str,
    evento: str,
    id_sesion: str = "",
    data: dict[str, Any] | None = None,
    nivel: str = "info",
    *,
    funcion: str | None = None,
) -> None:
    """Emite un evento con nombre estable, función de origen y atributos saneados."""
    nivel_normalizado = nivel.lower()
    metodo = {
        "debug": _logger.debug,
        "error": _logger.error,
        "warning": _logger.warning,
    }.get(nivel_normalizado, _logger.info)
    if not _logger.isEnabledFor(
        {"debug": logging.DEBUG, "error": logging.ERROR, "warning": logging.WARNING}.get(
            nivel_normalizado, logging.INFO
        )
    ):
        return

    sesion = id_sesion or _sesion_actual.get()
    entrada = {
        "ts": datetime.now(UTC).isoformat(),
        "nivel": nivel_normalizado.upper(),
        "sesion": _sesion_para_log(sesion),
        "evento": f"{nodo}.{evento}",
        "nodo": nodo,
        "accion": evento,
        "funcion": funcion or _funcion_llamadora(),
        "data": _sanear(data or {}),
    }
    metodo(json.dumps(entrada, ensure_ascii=False, default=str))


def log_inicio_turno(id_sesion: str, pregunta: str) -> None:
    """Marca el turno y limita la pregunta a través del saneamiento central."""
    _sesion_actual.set(id_sesion or "desconocida")
    log_paso("turno", "iniciado", id_sesion, {"pregunta": pregunta, "chars": len(pregunta)})


def log_fin_turno(id_sesion: str, respuesta: str, nodos: list[str]) -> None:
    """Cierra el turno con recorrido y tamaño, sin duplicar toda la respuesta."""
    log_paso(
        "turno",
        "finalizado",
        id_sesion,
        {"respuesta_chars": len(respuesta), "nodos_visitados": nodos},
    )


class _EstadoRastreo(threading.local):
    def __init__(self) -> None:
        self.inicios: dict[int, tuple[float, contextvars.Token[str] | None]] = {}


_estado_rastreo = _EstadoRastreo()


def _es_funcion_agente(frame: FrameType) -> bool:
    modulo = str(frame.f_globals.get("__name__", ""))
    return (
        (modulo == "agente" or modulo.startswith("agente."))
        and modulo != _MODULO_LOGGER
        and not frame.f_code.co_name.startswith("<")
    )


def _nombre_funcion(frame: FrameType) -> str:
    return f"{frame.f_globals.get('__name__', 'agente')}.{frame.f_code.co_qualname}"


def _sesion_desde_frame(frame: FrameType) -> str | None:
    candidato = frame.f_locals.get("id_sesion")
    estado = frame.f_locals.get("estado")
    if not isinstance(candidato, str) and isinstance(estado, dict):
        candidato = estado.get("id_sesion")
    body = frame.f_locals.get("body")
    if not isinstance(candidato, str) and body is not None:
        candidato = getattr(body, "id_sesion", None)
    if not isinstance(candidato, str):
        return None
    return candidato.strip()[:120] or None


def _perfil_funciones(frame: FrameType, evento: str, _arg: Any) -> None:
    """Mide funciones en DEBUG y emite una única línea al finalizar cada llamada."""
    if evento not in {"call", "return"} or not _es_funcion_agente(frame):
        return
    clave = id(frame)
    if evento == "call":
        sesion = _sesion_desde_frame(frame)
        token = _sesion_actual.set(sesion) if sesion and sesion != _sesion_actual.get() else None
        _estado_rastreo.inicios[clave] = (time.perf_counter(), token)
        return

    inicio = _estado_rastreo.inicios.pop(clave, None)
    if inicio is None:
        return
    iniciado_en, token = inicio
    nombre = _nombre_funcion(frame)
    log_paso(
        "funcion",
        "finalizada",
        data={"duracion_ms": round((time.perf_counter() - iniciado_en) * 1000, 3)},
        nivel="debug",
        funcion=nombre,
    )
    if token is not None:
        _sesion_actual.reset(token)


def activar_rastreo_funciones() -> None:
    """Activa el perfil técnico solo cuando DEBUG puede mostrarlo."""
    if sys.getprofile() is _perfil_funciones:
        return
    sys.setprofile(_perfil_funciones)
    threading.setprofile(_perfil_funciones)


if booleano("LOG_FUNCIONES", True) and _logger.isEnabledFor(logging.DEBUG):
    activar_rastreo_funciones()
