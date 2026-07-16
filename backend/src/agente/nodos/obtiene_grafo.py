"""Segundo nodo: obtiene la descripción cacheada del schema Neo4j vivo."""

from __future__ import annotations

from typing import Any

from agente.db.neo4j import construir_schema_texto
from agente.grafo.estado import EstadoAgente
from agente.nodos.base import Nodo
from agente.observabilidad.logger import log_paso


class ObtieneGrafo(Nodo):
    """Coloca el schema textual en el estado para el flujo dinámico y la validación."""

    nombre = "obtiene_grafo"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        schema_texto = construir_schema_texto()
        log_paso(self.nombre, "schema_obtenido", sesion, {"chars": len(schema_texto)})
        return {"schema_texto": schema_texto}
