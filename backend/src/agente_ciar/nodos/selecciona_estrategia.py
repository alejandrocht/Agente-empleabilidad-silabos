"""Selecciona caché, plantilla determinista o generación dinámica, en ese orden de costo."""

from __future__ import annotations

import re
from typing import Any

from agente_ciar.cache.consultas import buscar as buscar_cache
from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.memoria.conversacional import actualizar_entidades
from agente_ciar.nodos.base import Nodo
from agente_ciar.observabilidad.logger import log_paso
from agente_ciar.plantillas.motor import (
    buscar_intencion,
    buscar_plantilla,
    renderizar,
    resolver_entidades,
)

_REFERENCIA = re.compile(r"\b(es[ae]|es[eo]|la anterior|el anterior|dicha|dicho)\b", re.IGNORECASE)


class SeleccionaEstrategia(Nodo):
    """Evita trabajo remoto cuando una respuesta o consulta determinista ya existe."""

    nombre = "selecciona_estrategia"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        pregunta = str(estado.get("pregunta", ""))
        sesion = str(estado.get("id_sesion", "") or "")
        entidades = list(estado.get("entidades", []))
        log_paso(self.nombre, "inicio", sesion)

        # Solo una referencia explícita puede heredar la entidad activa; un nombre nuevo debe ganar.
        if _REFERENCIA.search(pregunta):
            entidades = list(estado.get("entidades_contexto", []))

        entrada_cache = buscar_cache(pregunta, entidades)
        if entrada_cache:
            log_paso(self.nombre, "cache_hit", sesion)
            return {**entrada_cache, "entidades": entidades, "estrategia": "cache"}
        log_paso(self.nombre, "cache_miss", sesion)

        # Primero se intenta una plantilla ya parametrizada, incluyendo referencias de memoria.
        plantilla = buscar_plantilla(pregunta, entidades)
        if not plantilla:
            intencion = buscar_intencion(pregunta)
            if intencion:
                try:
                    entidades = resolver_entidades(intencion, pregunta, entidades)
                    plantilla = buscar_plantilla(pregunta, entidades)
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
                log_paso(self.nombre, "cache_hit", sesion)
                return {**entrada_cache, "entidades": entidades, "estrategia": "cache"}
            cypher = renderizar(plantilla, entidades)
            actualizar_entidades(sesion, entidades)
            log_paso(self.nombre, "plantilla_usada", sesion, {"id": plantilla["id"]})
            return {
                "cypher": cypher,
                "entidades": entidades,
                "estrategia": "plantilla",
                "plantilla_id": plantilla["id"],
            }

        log_paso(self.nombre, "generacion_dinamica", sesion)
        return {"entidades": [], "estrategia": "dinamica"}
