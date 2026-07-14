"""Primer nodo: limpia, protege y contextualiza la pregunta del turno."""

from __future__ import annotations

from typing import Any

from agente_ciar.grafo.estado import EstadoAgente
from agente_ciar.guardas.entrada import validar_entrada
from agente_ciar.memoria.conversacional import entidades_activas, formatear
from agente_ciar.nodos.base import Nodo
from agente_ciar.observabilidad.logger import log_inicio_turno, log_paso

SALUDOS = {
    "adios",
    "adiós",
    "buenas",
    "buenas noches",
    "buenas tardes",
    "buenos dias",
    "buenos días",
    "chau",
    "gracias",
    "hello",
    "hey",
    "hi",
    "hola",
    "ok",
    "ola",
    "que tal",
    "qué tal",
    "saludos",
}
AYUDA = (
    "Soy el agente del CIAR. Pregúntame sobre carreras, cursos, empresas, ofertas, "
    "competencias y otros datos académicos o laborales."
)


class ObtienePregunta(Nodo):
    """Reinicia campos del turno sin borrar la memoria externa de la sesión."""

    nombre = "obtiene_pregunta"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        pregunta = str(estado.get("pregunta", "")).strip()
        sesion = str(estado.get("id_sesion", "") or "")
        log_inicio_turno(sesion, pregunta)
        log_paso(self.nombre, "inicio", sesion)

        # MemorySaver conserva el checkpoint; estos campos se reinician para impedir fugas.
        cambios: dict[str, Any] = {
            "pregunta": pregunta,
            "id_sesion": sesion,
            "memoria_texto": formatear(sesion),
            "entidades_contexto": entidades_activas(sesion),
            "entidades": [],
            "schema_texto": None,
            "cypher": None,
            "filas": [],
            "respuesta": None,
            "intentos": 0,
            "error": None,
            "estrategia": None,
            "plantilla_id": None,
        }

        segura, motivo = validar_entrada(pregunta)
        if not segura:
            cambios["error"] = motivo
            log_paso(self.nombre, "entrada_rechazada", sesion, {"motivo": motivo}, "warning")
            return cambios

        # Los saludos concluyen aquí y no consultan ni Neo4j ni OpenAI.
        clave = pregunta.lower().strip("¿?¡!.")
        if clave in SALUDOS:
            cambios["respuesta"] = AYUDA
            log_paso(self.nombre, "saludo", sesion)
            return cambios

        log_paso(self.nombre, "pregunta_aceptada", sesion, {"chars": len(pregunta)})
        return cambios
