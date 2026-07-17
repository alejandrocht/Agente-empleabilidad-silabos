"""Decisiones deterministas del grafo con una razón auditable por cada salto."""

from __future__ import annotations

import inspect

from agente.grafo.estado import EstadoAgente
from agente.observabilidad.logger import log_paso

MAX_INTENTOS = 2


def _decision(estado: EstadoAgente, desde: str, hacia: str, motivo: str) -> str:
    frame = inspect.currentframe()
    llamadora = frame.f_back if frame is not None else None
    funcion = (
        f"{llamadora.f_globals.get('__name__', __name__)}.{llamadora.f_code.co_qualname}"
        if llamadora is not None
        else f"{__name__}._decision"
    )
    log_paso(
        "decision",
        "ruta_seleccionada",
        str(estado.get("id_sesion", "") or ""),
        {
            "desde": desde,
            "hacia": hacia,
            "motivo": motivo,
            "estrategia": estado.get("estrategia"),
            "intentos": estado.get("intentos", 0),
            "tiene_error": bool(estado.get("error")),
        },
        funcion=funcion,
    )
    return hacia


def ruta_tras_pregunta(estado: EstadoAgente) -> str:
    """Los saludos y entradas inválidas responden sin abrir conexiones externas."""
    if estado.get("respuesta") or estado.get("error"):
        motivo = "respuesta directa disponible" if estado.get("respuesta") else "entrada rechazada"
        return _decision(estado, "obtiene_pregunta", "devuelve_resultado", motivo)
    return _decision(estado, "obtiene_pregunta", "obtiene_grafo", "pregunta válida")


def ruta_tras_estrategia(estado: EstadoAgente) -> str:
    """Salta los pasos que la caché o la plantilla ya resolvieron."""
    estrategia = estado.get("estrategia", "dinamica")
    if estrategia == "cache":
        return _decision(estado, "selecciona_estrategia", "analiza_resultado", "cache hit")
    if estrategia == "plantilla":
        return _decision(
            estado, "selecciona_estrategia", "valida_cypher", "plantilla determinista"
        )
    return _decision(
        estado, "selecciona_estrategia", "resuelve_entidad", "generación dinámica"
    )


def ruta_tras_validar(estado: EstadoAgente) -> str:
    """Ejecuta un Cypher válido, repara hasta el límite o devuelve el error."""
    if not estado.get("error"):
        return _decision(estado, "valida_cypher", "ejecuta_cypher", "Cypher válido")
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return _decision(
            estado, "valida_cypher", "genera_cypher", "Cypher inválido; quedan intentos"
        )
    return _decision(
        estado, "valida_cypher", "devuelve_resultado", "límite de intentos alcanzado"
    )


def ruta_tras_ejecutar(estado: EstadoAgente) -> str:
    """Analiza filas válidas o reintenta una consulta dinámica fallida."""
    if not estado.get("error"):
        return _decision(estado, "ejecuta_cypher", "analiza_resultado", "consulta ejecutada")
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return _decision(
            estado, "ejecuta_cypher", "genera_cypher", "ejecución fallida; quedan intentos"
        )
    return _decision(
        estado, "ejecuta_cypher", "devuelve_resultado", "límite de intentos alcanzado"
    )
