"""Genera y limpia una consulta Cypher dinámica usando el modelo OpenAI del rol."""

from __future__ import annotations

import json
import re
from typing import Any

from agente.grafo.estado import EstadoAgente
from agente.nodos.base import NodoLLM
from agente.observabilidad.logger import log_paso


def _limpiar_cypher(texto: str) -> str:
    """Elimina Markdown y prosa para conservar un único statement Cypher."""
    cypher = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.I | re.S).strip()
    if "```" in cypher:
        bloques = cypher.split("```")
        cypher = bloques[1] if len(bloques) > 1 else cypher
    cypher = re.sub(r"^\s*cypher\s*", "", cypher, flags=re.I).strip("` \n")
    if not cypher.lower().startswith(("match", "with", "return", "call")):
        coincidencia = re.search(r"\b(match|with|return|call)\b", cypher, flags=re.I)
        if coincidencia:
            cypher = cypher[coincidencia.start() :]
    return cypher.strip()


class GeneraCypher(NodoLLM):
    """Construye Cypher con schema, entidades verificadas, memoria y error previo."""

    nombre = "genera_cypher"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion, {"intento": estado.get("intentos", 0) + 1})
        entidades = json.dumps(estado.get("entidades", []), ensure_ascii=False)
        error = str(estado.get("error") or "")
        reparacion = f"La consulta anterior falló. Corrige este error:\n{error}" if error else ""
        prompt = (
            self.prompt.replace("{schema_texto}", str(estado.get("schema_texto", "")))
            .replace("{entidades}", entidades or "(ninguna)")
            .replace("{reparacion}", reparacion)
            .replace("{memoria}", str(estado.get("memoria_texto", "(sin memoria)")))
            .replace("{pregunta}", str(estado.get("pregunta", "")))
        )
        cypher = _limpiar_cypher(str(self.llm.invoke(prompt).content))
        intentos = estado.get("intentos", 0) + 1
        log_paso(
            self.nombre,
            "cypher_generado",
            sesion,
            {
                "cypher": cypher,
                "chars": len(cypher),
                "intento": intentos,
                "entidades_usadas": estado.get("entidades", []),
                "memoria_usada": estado.get("memoria_texto", ""),
                "reparacion_solicitada": bool(error),
                "error_anterior": error,
            },
        )
        return {
            "cypher": cypher,
            "error": None,
            "intentos": intentos,
            "estrategia": "dinamica",
        }
