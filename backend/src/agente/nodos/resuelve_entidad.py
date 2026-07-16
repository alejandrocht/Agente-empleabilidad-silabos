"""Detecta entidades con OpenAI y resuelve sus ids reales mediante consultas parametrizadas."""

from __future__ import annotations

import json
import unicodedata
from typing import Any

from agente.db.neo4j import ejecutar_lectura, introspeccionar_schema
from agente.grafo.estado import EstadoAgente
from agente.memoria.conversacional import actualizar_entidades
from agente.nodos.base import NodoLLM
from agente.observabilidad.logger import log_paso


def _normalizar(texto: str) -> str:
    """Normaliza el texto del candidato antes de pasarlo como parámetro a Neo4j."""
    descompuesto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in descompuesto if not unicodedata.combining(c)).strip()


def _extraer_json(texto: str) -> dict[str, Any]:
    """Extrae el primer objeto JSON aunque el modelo añada delimitadores accidentales."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fin <= inicio:
        return {"entidades": []}
    try:
        dato = json.loads(texto[inicio : fin + 1])
        return dato if isinstance(dato, dict) else {"entidades": []}
    except json.JSONDecodeError:
        return {"entidades": []}


def _prop_nombre(propiedades: list[str]) -> str | None:
    """Elige la propiedad visible de nombre y excluye el campo interno ``nombre_norm``."""
    if "nombre" in propiedades:
        return "nombre"
    return next(
        (p for p in propiedades if p.startswith("nombre_") and p != "nombre_norm"),
        None,
    )


def _prop_id(propiedades: list[str]) -> str | None:
    """Elige el identificador estable del label para usarlo después en Cypher."""
    return next((p for p in propiedades if p.startswith("id_")), None)


class ResuelveEntidad(NodoLLM):
    """Convierte menciones libres en entidades verificadas contra el grafo vivo."""

    nombre = "resuelve_entidad"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        prompt = self.prompt.replace(
            "{memoria}", str(estado.get("memoria_texto", "(sin memoria)"))
        ).replace("{pregunta}", str(estado.get("pregunta", "")))
        candidatos = _extraer_json(str(self.llm.invoke(prompt).content)).get("entidades", [])
        if not isinstance(candidatos, list) or not candidatos:
            log_paso(self.nombre, "sin_entidades", sesion)
            return {"entidades": []}

        intro = introspeccionar_schema()
        resueltas: list[dict[str, Any]] = []
        for candidato in candidatos:
            if not isinstance(candidato, dict):
                continue
            texto = _normalizar(str(candidato.get("texto", "")))
            label_sugerido = str(candidato.get("label", ""))
            if not texto:
                continue

            # Se usa el label sugerido solo si existe; si no, se exploran labels con nombre.
            labels = (
                [label_sugerido]
                if label_sugerido in intro["labels"]
                else [label for label, props in intro["props"].items() if _prop_nombre(props)]
            )
            for label in labels:
                propiedades = intro["props"].get(label, [])
                nombre, identificador = _prop_nombre(propiedades), _prop_id(propiedades)
                if not nombre:
                    continue

                palabras = texto.split()
                condiciones = [
                    f"apoc.text.clean(toString(n.`{nombre}`)) CONTAINS apoc.text.clean($q{i})"
                    for i in range(len(palabras))
                ]
                retorno_id = f", n.`{identificador}` AS id" if identificador else ""
                cypher = (
                    f"MATCH (n:`{label}`) WHERE {' AND '.join(condiciones)} "
                    f"RETURN n.`{nombre}` AS nombre{retorno_id} LIMIT 1"
                )
                parametros = {f"q{i}": palabra for i, palabra in enumerate(palabras)}
                filas = ejecutar_lectura(cypher, parametros)
                if filas:
                    resueltas.append(
                        {
                            "texto": texto,
                            "label": label,
                            "nombre": filas[0].get("nombre"),
                            "id": filas[0].get("id"),
                        }
                    )
                    break

        actualizar_entidades(sesion, resueltas)
        log_paso(self.nombre, "entidades_resueltas", sesion, {"cantidad": len(resueltas)})
        return {"entidades": resueltas}
