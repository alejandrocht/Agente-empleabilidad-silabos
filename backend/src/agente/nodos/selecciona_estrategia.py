"""Selecciona caché, plantilla determinista o generación dinámica, en ese orden de costo."""

from __future__ import annotations

import re
from typing import Any

from agente.cache.consultas import buscar as buscar_cache
from agente.grafo.estado import EstadoAgente
from agente.memoria.conversacional import actualizar_entidades
from agente.nodos.base import Nodo
from agente.observabilidad.logger import log_paso
from agente.plantillas.motor import (
    buscar_intencion,
    buscar_plantilla,
    renderizar,
    resolver_entidades,
)

_REFERENCIA_ANTERIOR = re.compile(r"\b(la|el)\s+anterior\b", re.IGNORECASE)
_REFERENCIA_PRIMERA = re.compile(
    r"\b(la primera|el primero)(\s+mencionad[ao])?\b", re.IGNORECASE
)
_REFERENCIA_ACTIVA = re.compile(
    r"\b(es[aeo]|est[aeo]|dicha|dicho|la [uú]ltima|el [uú]ltimo)\b", re.IGNORECASE
)


def _desde_historial(
    historial: dict[str, list[dict[str, Any]]], posicion: int
) -> list[dict[str, Any]]:
    """Selecciona una posición disponible de cada historial de label."""
    seleccionadas: list[dict[str, Any]] = []
    for entidades in historial.values():
        if entidades and -len(entidades) <= posicion < len(entidades):
            seleccionadas.append(entidades[posicion])
    return seleccionadas


def _resolver_referencia(estado: EstadoAgente, pregunta: str) -> list[dict[str, Any]] | None:
    """Resuelve referencias ordinales antes de intentar reconocer una entidad nueva."""
    historial = dict(estado.get("entidades_historial", {}))
    if _REFERENCIA_ANTERIOR.search(pregunta):
        anteriores = [entidades[-2] for entidades in historial.values() if len(entidades) >= 2]
        return anteriores
    if _REFERENCIA_PRIMERA.search(pregunta):
        return _desde_historial(historial, 0)
    if _REFERENCIA_ACTIVA.search(pregunta):
        return list(estado.get("entidades_contexto", []))
    return None


class SeleccionaEstrategia(Nodo):
    """Evita trabajo remoto cuando una respuesta o consulta determinista ya existe."""

    nombre = "selecciona_estrategia"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        pregunta = str(estado.get("pregunta", ""))
        sesion = str(estado.get("id_sesion", "") or "")
        entidades = list(estado.get("entidades", []))
        log_paso(
            self.nombre,
            "evaluacion_iniciada",
            sesion,
            {
                "pregunta": pregunta,
                "entidades_recibidas": entidades,
                "entidades_en_memoria": estado.get("entidades_contexto", []),
                "historial_en_memoria": estado.get("entidades_historial", {}),
            },
        )

        # Una referencia usa el historial; sin referencia, un nombre nuevo debe ganar.
        referenciadas = _resolver_referencia(estado, pregunta)
        if referenciadas is not None:
            entidades = referenciadas
            log_paso(
                self.nombre,
                "referencia_resuelta",
                sesion,
                {
                    "tipo": (
                        "anterior"
                        if _REFERENCIA_ANTERIOR.search(pregunta)
                        else "primera"
                        if _REFERENCIA_PRIMERA.search(pregunta)
                        else "activa"
                    ),
                    "entidades_seleccionadas": entidades,
                },
            )

        entrada_cache = buscar_cache(pregunta, entidades)
        if entrada_cache:
            log_paso(
                self.nombre,
                "estrategia_seleccionada",
                sesion,
                {
                    "estrategia": "cache",
                    "motivo": "coincidencia exacta de pregunta y entidades",
                    "entidades": entidades,
                    "cypher_cacheado": entrada_cache.get("cypher"),
                    "filas_cacheadas": len(entrada_cache.get("filas", [])),
                },
            )
            return {**entrada_cache, "entidades": entidades, "estrategia": "cache"}
        log_paso(
            self.nombre,
            "cache_descartada",
            sesion,
            {"motivo": "sin coincidencia vigente", "entidades_usadas_en_clave": entidades},
        )

        # Primero se intenta una plantilla ya parametrizada, incluyendo referencias de memoria.
        plantilla = buscar_plantilla(pregunta, entidades)
        if not plantilla:
            intencion = buscar_intencion(pregunta)
            if intencion:
                log_paso(
                    self.nombre,
                    "intencion_plantilla_detectada",
                    sesion,
                    {
                        "plantilla_id": intencion["id"],
                        "parametros_requeridos": intencion["params"],
                    },
                )
                try:
                    entidades = resolver_entidades(intencion, pregunta, entidades)
                    plantilla = buscar_plantilla(pregunta, entidades)
                    log_paso(
                        self.nombre,
                        "entidades_plantilla_resueltas",
                        sesion,
                        {"entidades": entidades, "plantilla_habilitada": bool(plantilla)},
                    )
                except Exception as exc:
                    # Si la resolución barata falla, el flujo dinámico conserva la funcionalidad.
                    log_paso(
                        self.nombre,
                        "resolucion_plantilla_fallida",
                        sesion,
                        {"error": str(exc)[:200]},
                        "warning",
                    )

        if plantilla:
            # Tras resolver ids se revisa otra vez la caché con su clave completa.
            entrada_cache = buscar_cache(pregunta, entidades)
            if entrada_cache:
                log_paso(
                    self.nombre,
                    "estrategia_seleccionada",
                    sesion,
                    {
                        "estrategia": "cache",
                        "motivo": "hit después de resolver entidades de plantilla",
                        "entidades": entidades,
                        "cypher_cacheado": entrada_cache.get("cypher"),
                        "filas_cacheadas": len(entrada_cache.get("filas", [])),
                    },
                )
                return {**entrada_cache, "entidades": entidades, "estrategia": "cache"}
            cypher = renderizar(plantilla, entidades)
            actualizar_entidades(sesion, entidades)
            log_paso(
                self.nombre,
                "estrategia_seleccionada",
                sesion,
                {
                    "estrategia": "plantilla",
                    "motivo": "intención determinista y parámetros completos",
                    "plantilla_id": plantilla["id"],
                    "entidades": entidades,
                    "cypher_renderizado": cypher,
                },
            )
            return {
                "cypher": cypher,
                "entidades": entidades,
                "estrategia": "plantilla",
                "plantilla_id": plantilla["id"],
            }

        log_paso(
            self.nombre,
            "estrategia_seleccionada",
            sesion,
            {
                "estrategia": "dinamica",
                "motivo": "sin cache ni plantilla aplicable",
                "entidades_descartadas": entidades,
            },
        )
        return {"entidades": [], "estrategia": "dinamica"}
