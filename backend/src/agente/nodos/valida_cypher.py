"""Valida el Cypher con la guarda central, el schema vivo y ``EXPLAIN``."""

from __future__ import annotations

from typing import Any

from agente.grafo.estado import EstadoAgente
from agente.guardas.cypher import validar_consulta
from agente.nodos.base import Nodo
from agente.observabilidad.logger import log_paso


class ValidaCypher(Nodo):
    """Marca el error en estado sin lanzar para permitir una reparación acotada."""

    nombre = "valida_cypher"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        error = validar_consulta(str(estado.get("cypher", "") or ""))
        if error:
            log_paso(
                self.nombre,
                "cypher_rechazado",
                sesion,
                {
                    "cypher": estado.get("cypher"),
                    "motivo": error,
                    "intento": estado.get("intentos", 0),
                },
                "warning",
            )
        else:
            log_paso(
                self.nombre,
                "cypher_valido",
                sesion,
                {
                    "cypher": estado.get("cypher"),
                    "validaciones": ["solo lectura", "schema", "EXPLAIN"],
                },
            )
        return {"error": error}
