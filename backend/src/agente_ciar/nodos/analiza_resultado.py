"""Redacta filas con OpenAI en flujo dinámico y sin LLM en caché o plantillas."""

from __future__ import annotations

import json
from typing import Any

from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.nodos.base import NodoLLM
from agente_ciar.observabilidad.logger import log_paso


def _redactar_determinista(filas: list[dict[str, Any]]) -> str:
    """Convierte resultados comunes en español legible sin costo ni alucinaciones."""
    if not filas:
        return "No encontré datos para esa consulta."
    if len(filas) == 1 and len(filas[0]) == 1:
        clave, valor = next(iter(filas[0].items()))
        etiqueta = clave.replace("_", " ")
        return f"El total es {valor}." if clave == "total" else f"{etiqueta.capitalize()}: {valor}."

    # Cada fila se limita para mantener la respuesta bajo el máximo del inspector.
    lineas = ["Estos son los resultados:"]
    for fila in filas[:25]:
        detalle = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in fila.items())
        lineas.append(f"- {detalle[:160]}")
    return "\n".join(lineas)[:2000]


class AnalizaResultado(NodoLLM):
    """Usa el modelo solo cuando el Cypher también fue generado dinámicamente."""

    nombre = "analiza_resultado"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)

        # Un hit de caché ya conserva la respuesta auditada del turno original.
        if estado.get("estrategia") == "cache" and estado.get("respuesta"):
            log_paso(self.nombre, "respuesta_cache", sesion)
            return {"respuesta": estado["respuesta"]}

        filas = list(estado.get("filas", []))
        if estado.get("estrategia") == "plantilla":
            respuesta = _redactar_determinista(filas)
            log_paso(self.nombre, "respuesta_determinista", sesion)
            return {"respuesta": respuesta}

        # El flujo dinámico conserva el redactor LLM para preguntas no cubiertas por plantillas.
        prompt = self.prompt.replace("{pregunta}", str(estado.get("pregunta", ""))).replace(
            "{filas}", json.dumps(filas, ensure_ascii=False, default=str)
        )
        respuesta = str(self.llm.invoke(prompt).content).strip()
        log_paso(self.nombre, "respuesta_llm", sesion, {"chars": len(respuesta)})
        return {"respuesta": respuesta}
