"""Valida el Cypher con la guarda central, el schema vivo y ``EXPLAIN``."""

from __future__ import annotations

from typing import Any

from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.guardas.cypher import validar_consulta
from agente_ciar.nodos.base import Nodo
from agente_ciar.observabilidad.logger import log_paso


class ValidaCypher(Nodo):
    """Marca el error en estado sin lanzar para permitir una reparación acotada."""

    nombre = "valida_cypher"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        error = validar_consulta(str(estado.get("cypher", "") or ""))
        if error:
            log_paso(self.nombre, "cypher_rechazado", sesion, {"error": error[:200]}, "warning")
        else:
            log_paso(self.nombre, "cypher_valido", sesion)
        return {"error": error}
