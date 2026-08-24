"""Bounded routing before any schema, Cypher generation, or database access."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from agente.grafo.estado import Estado
from agente.utils.conversacion import (
    RESPUESTA_FUERA_DE_ALCANCE,
    respuesta_conversacional,
)
from agente.utils.logger import log_event

Route = Literal["conversacion", "cypher", "finalizar"]

_GRAPH_TERMS = frozenset(
    {
        "academica",
        "academico",
        "academicas",
        "academicos",
        "carrera",
        "carreras",
        "cargo",
        "cargos",
        "curso",
        "cursos",
        "empresa",
        "empresas",
        "empleabilidad",
        "empleo",
        "facultad",
        "facultades",
        "herramienta",
        "herramientas",
        "habilidad",
        "habilidades",
        "industria",
        "industrias",
        "job",
        "jobs",
        "laboral",
        "laborales",
        "oferta",
        "ofertas",
        "puesto",
        "puestos",
        "salario",
        "salarios",
        "sueldo",
        "sueldos",
        "trabajo",
        "trabajos",
        "vacante",
        "vacantes",
    }
)
_DOMAIN_TERMS = _GRAPH_TERMS | frozenset(
    {
        "alineacion",
        "alineamiento",
        "aprendizaje",
        "aprendizajes",
        "brecha",
        "brechas",
        "competencia",
        "competencias",
        "comparar",
        "comparacion",
        "curricular",
        "curriculo",
        "demanda",
        "diferencia",
        "egresado",
        "egresados",
        "ensenanza",
        "exige",
        "exigencia",
        "formacion",
        "mercado",
        "perfil",
        "perfiles",
        "requerimiento",
        "requerimientos",
        "requisito",
        "requisitos",
        "silabo",
        "sillabo",
        "ulima",
        "universidad",
    }
)


def _tokens(text: str) -> frozenset[str]:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return frozenset(re.findall(r"[a-z0-9]+", without_accents))


def orquestador(estado: Estado) -> Estado:
    """Select a non-domain conversation or the guarded read-only graph route."""
    if estado.get("error"):
        return {"ruta": "finalizar"}

    question = estado.get("pregunta_contextualizada") or estado.get("pregunta")
    if not isinstance(question, str) or not question.strip():
        return {"ruta": "finalizar", "error": "orchestrator_failed"}

    local_answer = respuesta_conversacional(question)
    if local_answer is not None:
        log_event("orchestrator", "route_selected", route="conversacion", local=True)
        return {"ruta": "conversacion", "respuesta": local_answer}

    tokens = _tokens(question)
    if not tokens & _DOMAIN_TERMS:
        log_event("orchestrator", "route_selected", route="finalizar", reason="out_of_scope")
        return {
            "ruta": "finalizar",
            "respuesta": RESPUESTA_FUERA_DE_ALCANCE,
            "error": "fuera_de_alcance",
        }

    route: Route = "cypher" if tokens & _GRAPH_TERMS else "conversacion"
    log_event("orchestrator", "route_selected", route=route, local=False)
    return {"ruta": route}
