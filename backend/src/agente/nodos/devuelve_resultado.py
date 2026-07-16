"""Inspecciona, memoriza y entrega la respuesta final del turno."""

from __future__ import annotations

import json
import re
from typing import Any

from agente.cache.consultas import guardar as guardar_cache
from agente.config.settings import booleano
from agente.grafo.estado import EstadoAgente
from agente.llm.fabrica import obtener_llm
from agente.memoria.bloques import registrar_mensaje
from agente.memoria.conversacional import actualizar_entidades, formatear
from agente.nodos.base import Nodo
from agente.observabilidad.logger import log_paso

_CJK = re.compile(r"[一-鿿]")


def _inspeccionar(respuesta: str) -> tuple[bool, str]:
    """Rechaza respuestas vacías, desmedidas o con caracteres CJK inesperados."""
    if not respuesta or len(respuesta.strip()) < 10:
        return False, "respuesta vacía o demasiado corta"
    if len(respuesta) > 2000:
        return False, "respuesta demasiado larga"
    if _CJK.search(respuesta):
        return False, "respuesta contiene caracteres no permitidos (CJK)"
    return True, ""


def _juez_llm(estado: EstadoAgente, respuesta: str) -> bool:
    """Pide al inspector opcional que responda ``OK`` solo si no se inventaron datos."""
    contenido = json.dumps(estado.get("filas", []), ensure_ascii=False, default=str)
    prompt = (
        "Audita una respuesta del agente CIAR. Responde solo OK o RECHAZAR. "
        "Rechaza si contradice o inventa datos.\n"
        f"Pregunta: {estado.get('pregunta', '')}\nFilas: {contenido}\nRespuesta: {respuesta}"
    )
    veredicto = str(obtener_llm("inspector").invoke(prompt).content).strip().upper()
    return veredicto == "OK"


def _limpieza_turno() -> dict[str, Any]:
    """Retira datos pesados o transitorios al cerrar el turno."""
    return {
        "schema_texto": None,
        "filas": [],
        "entidades": [],
        "entidades_contexto": [],
        "entidades_historial": {},
        "cypher": None,
        "error": None,
        "estrategia": None,
        "plantilla_id": None,
    }


def _mensaje_error_publico(error: str) -> str:
    """Conserva rechazos de entrada útiles y oculta detalles de proveedores o consultas."""
    if error.startswith(("Pregunta demasiado larga", "La pregunta contiene patrones")):
        return error
    return "No pude completar la consulta de forma segura. Intenta reformular tu pregunta."


class DevuelveResultado(Nodo):
    """Produce una salida segura y actualiza caché y memoria solo cuando hubo éxito."""

    nombre = "devuelve_resultado"

    def __call__(self, estado: EstadoAgente) -> dict[str, Any]:
        sesion = str(estado.get("id_sesion", "") or "")
        log_paso(self.nombre, "inicio", sesion)
        error = str(estado.get("error") or "")
        respuesta = str(estado.get("respuesta") or "")
        if error:
            respuesta = _mensaje_error_publico(error)
        elif not respuesta:
            respuesta = "No encontré una respuesta para tu pregunta."

        valida, motivo = _inspeccionar(respuesta)
        if not valida:
            log_paso(self.nombre, "inspector_rechazo", sesion, {"motivo": motivo}, "warning")
            respuesta = "No pude generar una respuesta confiable para esta consulta."

        # El juez remoto es optativo y nunca impide devolver el resultado determinista válido.
        if booleano("INSPECTOR_LLM"):
            try:
                if not _juez_llm(estado, respuesta):
                    respuesta = (
                        "No pude verificar que la respuesta estuviera respaldada por los datos."
                    )
                    log_paso(self.nombre, "inspector_llm_rechazo", sesion, nivel="warning")
            except Exception as exc:
                log_paso(
                    self.nombre,
                    "inspector_llm_error",
                    sesion,
                    {"error": str(exc)[:200]},
                    "warning",
                )

        cypher = str(estado.get("cypher") or "")
        entidades = list(estado.get("entidades", []))
        if cypher and not error:
            # La respuesta auditada evita una segunda llamada LLM en un hit de caché.
            if estado.get("estrategia") != "cache":
                guardar_cache(
                    str(estado.get("pregunta", "")),
                    entidades,
                    cypher,
                    list(estado.get("filas", [])),
                    respuesta,
                )
            actualizar_entidades(sesion, entidades)
            registrar_mensaje(sesion, str(estado.get("pregunta", "")), respuesta)
            log_paso(self.nombre, "memoria_actualizada", sesion)

        log_paso(self.nombre, "respuesta_lista", sesion, {"chars": len(respuesta)})
        return {"respuesta": respuesta, "memoria_texto": formatear(sesion), **_limpieza_turno()}
