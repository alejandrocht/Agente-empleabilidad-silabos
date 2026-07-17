"""Ejecuta el Cypher ya validado mediante el cliente Neo4j de solo lectura."""

from __future__ import annotations

import time
from typing import Any

from agente.db.neo4j import ejecutar_lectura
from agente.grafo.estado import EstadoAgente
from agente.nodos.base import Nodo
from agente.observabilidad.logger import log_paso


class EjecutaCypher(Nodo):
    """Guarda filas o un error recuperable para que el enrutado decida el siguiente paso."""

    nombre = "ejecuta_cypher"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        cypher = str(estado.get("cypher", "") or "")
        inicio = time.perf_counter()
        try:
            filas = ejecutar_lectura(cypher)
        except Exception as exc:
            error = f"Error al ejecutar en Neo4j: {exc}"
            log_paso(
                self.nombre,
                "error",
                sesion,
                {
                    "cypher": cypher,
                    "error": error,
                    "duracion_ms": round((time.perf_counter() - inicio) * 1000, 2),
                },
                "error",
            )
            return {"filas": [], "error": error}
        log_paso(
            self.nombre,
            "filas_obtenidas",
            sesion,
            {
                "cypher": cypher,
                "cantidad": len(filas),
                "filas": filas,
                "duracion_ms": round((time.perf_counter() - inicio) * 1000, 2),
            },
        )
        return {"filas": filas, "error": None}
