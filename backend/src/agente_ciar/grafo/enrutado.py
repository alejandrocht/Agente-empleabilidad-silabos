"""Decisiones deterministas del grafo, separadas de su construcción."""

from __future__ import annotations

from agente_ciar.grafo.estado import EstadoAgente

MAX_INTENTOS = 2


def ruta_tras_pregunta(estado: EstadoAgente) -> str:
    """Los saludos y entradas inválidas responden sin abrir conexiones externas."""
    if estado.get("respuesta") or estado.get("error"):
        return "devuelve_resultado"
    return "obtiene_grafo"


def ruta_tras_estrategia(estado: EstadoAgente) -> str:
    """Salta los pasos que la caché o la plantilla ya resolvieron."""
    estrategia = estado.get("estrategia", "dinamica")
    if estrategia == "cache":
        return "analiza_resultado"
    if estrategia == "plantilla":
        return "valida_cypher"
    return "resuelve_entidad"


def ruta_tras_validar(estado: EstadoAgente) -> str:
    """Ejecuta un Cypher válido, repara hasta el límite o devuelve el error."""
    if not estado.get("error"):
        return "ejecuta_cypher"
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return "genera_cypher"
    return "devuelve_resultado"


def ruta_tras_ejecutar(estado: EstadoAgente) -> str:
    """Analiza filas válidas o reintenta una consulta dinámica fallida."""
    if not estado.get("error"):
        return "analiza_resultado"
    if estado.get("intentos", 0) < MAX_INTENTOS:
        return "genera_cypher"
    return "devuelve_resultado"
