"""Redacta filas con OpenAI en flujo dinámico y sin LLM en caché o plantillas."""

from __future__ import annotations

import json
from typing import Any

from agente.grafo.estado import EstadoAgente
from agente.nodos.base import NodoLLM
from agente.observabilidad.logger import log_paso

_ETIQUETAS_PLURAL = {
    "carrera": "carreras",
    "curso": "cursos",
    "empresa": "empresas",
    "herramienta": "herramientas",
    "competencia": "competencias",
    "habilidad": "habilidades",
    "puesto": "puestos",
    "industria": "industrias",
    "oferta": "ofertas",
}


def _resumen_tabla(filas: list[dict[str, Any]]) -> str:
    """Describe una tabla sin repetir sus filas en texto plano."""
    primera_fila = filas[0] if filas else {}
    primera_columna = next(iter(primera_fila), "")
    etiqueta = _ETIQUETAS_PLURAL.get(primera_columna.lower(), "resultados")
    cantidad = len(filas)
    verbo = "Se encontró" if cantidad == 1 else "Se encontraron"
    sustantivo = (
        "resultado"
        if cantidad == 1 and etiqueta == "resultados"
        else etiqueta[:-1]
        if cantidad == 1
        else etiqueta
    )
    return f"{verbo} {cantidad} {sustantivo}. Revisa el detalle en la tabla."


def _redactar_determinista(filas: list[dict[str, Any]]) -> str:
    """Convierte resultados comunes en español legible sin costo ni alucinaciones."""
    if not filas:
        return "No encontré datos para esa consulta."
    if len(filas) == 1 and len(filas[0]) == 1:
        clave, valor = next(iter(filas[0].items()))
        etiqueta = clave.replace("_", " ")
        return f"El total es {valor}." if clave == "total" else f"{etiqueta.capitalize()}: {valor}."

    return _resumen_tabla(filas)


class AnalizaResultado(NodoLLM):
    """Usa el modelo solo cuando el Cypher también fue generado dinámicamente."""

    nombre = "analiza_resultado"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)

        # Un hit de caché ya conserva la respuesta auditada del turno original.
        if estado.get("estrategia") == "cache" and estado.get("respuesta"):
            log_paso(
                self.nombre,
                "respuesta_cache",
                sesion,
                {"respuesta": estado["respuesta"], "filas": estado.get("filas", [])},
            )
            return {"respuesta": estado["respuesta"]}

        filas = list(estado.get("filas", []))
        if estado.get("estrategia") == "plantilla":
            respuesta = _redactar_determinista(filas)
            log_paso(
                self.nombre,
                "respuesta_determinista",
                sesion,
                {"filas_recibidas": filas, "respuesta_generada": respuesta},
            )
            return {"respuesta": respuesta}

        # El flujo dinámico conserva el redactor LLM para preguntas no cubiertas por plantillas.
        prompt = self.prompt.replace("{pregunta}", str(estado.get("pregunta", ""))).replace(
            "{filas}", json.dumps(filas, ensure_ascii=False, default=str)
        )
        respuesta = str(self.llm.invoke(prompt).content).strip()
        log_paso(
            self.nombre,
            "respuesta_llm",
            sesion,
            {
                "filas_entregadas_al_modelo": filas,
                "respuesta_generada": respuesta,
                "chars": len(respuesta),
            },
        )
        return {"respuesta": respuesta}
