"""Observabilidad central del backend con salida legible o JSON.

LangSmith sigue observando las llamadas LLM cuando ``LANGSMITH_TRACING=true``. Este
módulo cubre los eventos propios del agente y, opcionalmente, la entrada y salida de
cada función Python del paquete ``agente``. Nunca registra argumentos ni retornos.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import threading
import time
from datetime import UTC, datetime
from types import FrameType
from typing import Any

from agente.config.settings import booleano, texto

NOMBRE_LOGGER = "agente"
_MODULO_LOGGER = __name__
_sesion_actual: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agente_sesion_log", default="desconocida"
)


class FormateadorLegible(logging.Formatter):
    """Convierte los eventos JSON internos en líneas compactas para la terminal."""

    def format(self, record: logging.LogRecord) -> str:
        mensaje = record.getMessage()
        try:
            entrada = json.loads(mensaje)
        except (json.JSONDecodeError, TypeError):
            return f"{record.levelname:<7} | {mensaje}"

        if not isinstance(entrada, dict):
            return f"{record.levelname:<7} | {mensaje}"

        hora = self._hora(str(entrada.get("ts", "")))
        sesion = str(entrada.get("sesion", "desconocida"))
        nodo = str(entrada.get("nodo", "evento"))
        evento = str(entrada.get("evento", ""))
        data = entrada.get("data", {})

        if nodo == "funcion" and isinstance(data, dict):
            detalle = self._funcion(evento, data)
        else:
            detalle = f"{nodo}.{evento}"
            datos = self._datos(data)
            if datos:
                detalle = f"{detalle} | {datos}"

        return f"{hora} | {record.levelname:<7} | {sesion} | {detalle}"

    @staticmethod
    def _hora(valor: str) -> str:
        try:
            fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return "--:--:--.---"
        return fecha.astimezone(UTC).strftime("%H:%M:%S.%f")[:-3]

    @staticmethod
    def _datos(data: Any) -> str:
        if not isinstance(data, dict):
            return json.dumps(data, ensure_ascii=False, default=str)
        return " ".join(
            f"{clave}={json.dumps(valor, ensure_ascii=False, default=str)}"
            for clave, valor in data.items()
        )

    @staticmethod
    def _funcion(evento: str, data: dict[str, Any]) -> str:
        nombre = str(data.get("nombre", "desconocida"))
        profundidad = min(int(data.get("profundidad", 0)), 20)
        sangria = "  " * profundidad
        if evento == "entrada":
            return f"{sangria}>> {nombre}()"
        duracion = float(data.get("duracion_ms", 0.0))
        return f"{sangria}<< {nombre}() [{duracion:.2f} ms]"


def _crear_formateador() -> logging.Formatter:
    formato = texto("LOG_FORMATO", "legible").lower()
    if formato == "json":
        return logging.Formatter("%(message)s")
    return FormateadorLegible()


def _crear_logger() -> logging.Logger:
    logger = logging.getLogger(NOMBRE_LOGGER)
    if not logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(stream_handler)
    for existing_handler in logger.handlers:
        existing_handler.setFormatter(_crear_formateador())
    nivel = texto("LOG_NIVEL", "INFO").upper()
    logger.setLevel(getattr(logging, nivel, logging.INFO))
    return logger


_logger = _crear_logger()


def log_paso(
    nodo: str,
    evento: str,
    id_sesion: str = "",
    data: dict[str, Any] | None = None,
    nivel: str = "info",
) -> None:
    """Registra un evento estructurado sin incluir secretos ni resultados completos."""
    sesion = id_sesion or _sesion_actual.get()
    entrada = {
        "ts": datetime.now(UTC).isoformat(),
        "sesion": sesion,
        "nodo": nodo,
        "evento": evento,
        "data": data or {},
    }
    mensaje = json.dumps(entrada, ensure_ascii=False, default=str)

    escritor = {"error": _logger.error, "warning": _logger.warning}.get(nivel, _logger.info)
    escritor(mensaje)


def log_inicio_turno(id_sesion: str, pregunta: str) -> None:
    """Marca el inicio del turno y asocia su sesión a las trazas de funciones."""
    _sesion_actual.set(id_sesion or "desconocida")
    log_paso("turno", "inicio", id_sesion, {"pregunta": pregunta[:120]})


def log_fin_turno(id_sesion: str, respuesta: str, nodos: list[str]) -> None:
    """Marca el cierre del turno con métricas pequeñas y los nodos visitados."""
    log_paso(
        "turno",
        "fin",
        id_sesion,
        {"respuesta_chars": len(respuesta), "nodos": nodos},
    )


class _EstadoRastreo(threading.local):
    """Pila independiente para medir funciones anidadas en cada hilo."""

    def __init__(self) -> None:
        self.inicios: dict[int, tuple[float, int, contextvars.Token[str] | None]] = {}


_estado_rastreo = _EstadoRastreo()


def _es_funcion_agente(frame: FrameType) -> bool:
    modulo = str(frame.f_globals.get("__name__", ""))
    es_modulo_agente = modulo == "agente" or modulo.startswith("agente.")
    # Comprensiones y expresiones generadoras emiten un evento por cada reanudación y
    # ocultan las funciones reales entre ruido de implementación.
    es_funcion_sintetica = frame.f_code.co_name.startswith("<")
    return es_modulo_agente and modulo != _MODULO_LOGGER and not es_funcion_sintetica


def _nombre_funcion(frame: FrameType) -> str:
    modulo = str(frame.f_globals.get("__name__", "agente"))
    return f"{modulo}.{frame.f_code.co_qualname}"


def _sesion_desde_frame(frame: FrameType) -> str | None:
    """Obtiene solo el identificador de sesión, sin inspeccionar ni serializar argumentos."""
    locales = frame.f_locals
    candidato = locales.get("id_sesion")
    estado = locales.get("estado")
    if not isinstance(candidato, str) and isinstance(estado, dict):
        candidato = estado.get("id_sesion")
    body = locales.get("body")
    if not isinstance(candidato, str) and body is not None:
        candidato = getattr(body, "id_sesion", None)
    if not isinstance(candidato, str):
        return None
    candidato = candidato.strip()
    return candidato[:120] or None


def _perfil_funciones(frame: FrameType, evento: str, _arg: Any) -> None:
    """Callback de bajo nivel limitado estrictamente a funciones del backend."""
    if evento not in {"call", "return"} or not _es_funcion_agente(frame):
        return

    clave = id(frame)
    if evento == "call":
        profundidad = len(_estado_rastreo.inicios)
        sesion = _sesion_desde_frame(frame)
        token = _sesion_actual.set(sesion) if sesion and sesion != _sesion_actual.get() else None
        _estado_rastreo.inicios[clave] = (time.perf_counter(), profundidad, token)
        log_paso(
            "funcion",
            "entrada",
            data={"nombre": _nombre_funcion(frame), "profundidad": profundidad},
        )
        return

    inicio = _estado_rastreo.inicios.pop(clave, None)
    if inicio is None:
        return
    iniciado_en, profundidad, token = inicio
    log_paso(
        "funcion",
        "salida",
        data={
            "nombre": _nombre_funcion(frame),
            "profundidad": profundidad,
            "duracion_ms": round((time.perf_counter() - iniciado_en) * 1000, 3),
        },
    )
    if token is not None:
        _sesion_actual.reset(token)


def activar_rastreo_funciones() -> None:
    """Activa trazas para el hilo actual y para los que se creen posteriormente."""
    if sys.getprofile() is _perfil_funciones:
        return
    sys.setprofile(_perfil_funciones)
    threading.setprofile(_perfil_funciones)


if booleano("LOG_FUNCIONES", True):
    activar_rastreo_funciones()
