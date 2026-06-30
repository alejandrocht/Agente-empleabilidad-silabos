"""
Nodo 7: analiza_resultado  (USA LLM)

Convierte las filas crudas que devolvio Neo4j en una respuesta en espanol, clara y
natural, para el usuario. Le pasa al LLM la pregunta original y las filas en JSON.
"""
from __future__ import annotations

import json

from estado import EstadoAgente
from nodos.nodo import NodoLLM


class AnalizaResultado(NodoLLM):
    """Redacta la respuesta final en espanol a partir de las filas de Neo4j."""

    nombre = "analiza_resultado"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Convertimos las filas a texto JSON para incluirlas en el prompt.
        # default=str evita errores si hay tipos raros (fechas, etc.).
        filas = estado.get("filas", [])
        filas_texto = json.dumps(filas, ensure_ascii=False, default=str)

        # Rellenamos los huecos del prompt. replace por las llaves { } literales.
        prompt = (
            self.prompt
            .replace("{pregunta}", estado.get("pregunta", ""))
            .replace("{filas}", filas_texto)
        )

        # Le pedimos al LLM que redacte la respuesta.
        respuesta = self.llm.invoke(prompt)
        # Guardamos el texto final en el estado.
        return {"respuesta": str(respuesta.content).strip()}
