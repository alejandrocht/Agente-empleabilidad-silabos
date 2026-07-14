"""Ejecuta el Cypher ya validado mediante el cliente Neo4j de solo lectura."""

from __future__ import annotations

from typing import Any

from agente_ciar.db.neo4j import ejecutar_lectura
from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.nodos.base import Nodo
from agente_ciar.observabilidad.logger import log_paso


class EjecutaCypher(Nodo):
    """Guarda filas o un error recuperable para que el enrutado decida el siguiente paso."""

    nombre = "ejecuta_cypher"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        try:
            filas = ejecutar_lectura(str(estado.get("cypher", "") or ""))
        except Exception as exc:
            error = f"Error al ejecutar en Neo4j: {exc}"
            log_paso(self.nombre, "error", sesion, {"error": error[:200]}, "error")
            return {"filas": [], "error": error}
        log_paso(self.nombre, "filas_obtenidas", sesion, {"cantidad": len(filas)})
        return {"filas": filas, "error": None}
