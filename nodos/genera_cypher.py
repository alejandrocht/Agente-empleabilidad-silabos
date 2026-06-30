"""
Nodo 4: genera_cypher  (USA LLM)

Le pide al LLM que convierta la pregunta del usuario en una consulta Cypher.
Le pasa: el schema del grafo, las entidades ya resueltas (con sus id_*) y la pregunta.
El resultado (texto Cypher) se limpia de adornos (markdown) y se guarda en el estado.
"""
from __future__ import annotations

import json
import re

from estado import EstadoAgente
from nodos.nodo import NodoLLM


def _limpiar_cypher(texto: str) -> str:
    """Quita adornos (```cypher ... ```) y deja solo la consulta."""
    cypher = (texto or "").strip()
    # Si viene en un bloque de codigo markdown, nos quedamos con el contenido del bloque.
    if "```" in cypher:
        bloques = cypher.split("```")
        cypher = bloques[1] if len(bloques) > 1 else cypher
    # Quitamos la palabra "cypher" si quedo al inicio (ej: "```cypher").
    cypher = re.sub(r"^\s*cypher\s*", "", cypher, flags=re.IGNORECASE).strip()
    # Quitamos comillas invertidas sueltas y espacios.
    return cypher.strip("`").strip()


class GeneraCypher(NodoLLM):
    """Genera la consulta Cypher a partir de la pregunta + schema + entidades."""

    nombre = "genera_cypher"

    def __call__(self, estado: EstadoAgente) -> dict:
        # Convertimos la lista de entidades resueltas a texto JSON legible para el prompt.
        entidades = estado.get("entidades", [])
        entidades_texto = json.dumps(entidades, ensure_ascii=False) if entidades else "(ninguna)"

        # Si en una pasada anterior hubo un error, lo inyectamos para que el LLM lo corrija.
        error_previo = estado.get("error")
        reparacion = ""
        if error_previo:
            reparacion = f"La consulta anterior fallo con este error, corrigela:\n{error_previo}"

        # Rellenamos los huecos del prompt. Usamos replace (no format) por las llaves { }.
        prompt = (
            self.prompt
            .replace("{schema_texto}", estado.get("schema_texto", ""))
            .replace("{entidades}", entidades_texto)
            .replace("{reparacion}", reparacion)
            .replace("{pregunta}", estado.get("pregunta", ""))
        )

        # Le pedimos el Cypher al LLM.
        respuesta = self.llm.invoke(prompt)
        # Limpiamos el texto para quedarnos solo con la consulta.
        cypher = _limpiar_cypher(str(respuesta.content))

        # Contamos este intento (el grafo usa este numero como tope de reintentos).
        intentos = estado.get("intentos", 0) + 1

        # Guardamos el Cypher, contamos el intento y limpiamos el error previo.
        return {"cypher": cypher, "error": None, "intentos": intentos}
