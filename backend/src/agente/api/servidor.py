"""API FastAPI que expone el mismo grafo auditado usado por la consola."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agente.config import settings as _settings  # noqa: F401
from agente.db.neo4j import obtener_driver
from agente.grafo.constructor import construir_grafo
from agente.guardas.entrada import MAX_CHARS, validar_entrada
from agente.observabilidad.logger import log_fin_turno, log_paso

# Construir el grafo no conecta Neo4j ni crea clientes OpenAI; ambos recursos son perezosos.
grafo = construir_grafo()
app = FastAPI(title="CIAR Agente API", version="2.0.0")


class ChatIn(BaseModel):
    """Entrada mínima del chat, limitada antes de entrar al flujo."""

    pregunta: str = Field(..., min_length=1, max_length=MAX_CHARS)
    id_sesion: str = Field(..., min_length=1, max_length=120)


def _json_safe(valor: Any) -> Any:
    """Convierte valores Neo4j o LangChain en estructuras serializables por FastAPI."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, dict):
        return {str(clave): _json_safe(item) for clave, item in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_json_safe(item) for item in valor]
    return str(valor)


def _error_externo(exc: Exception) -> tuple[int, str]:
    """Traduce fallos de proveedores a mensajes estables sin exponer credenciales o payloads."""
    nombre = type(exc).__name__
    if nombre == "RateLimitError":
        return 503, "El servicio de IA no tiene cuota disponible en este momento."
    if nombre in {"AuthenticationError", "PermissionDeniedError"}:
        return 503, "El servicio de IA no está configurado correctamente."
    if nombre in {"APIConnectionError", "APITimeoutError"}:
        return 503, "No se pudo conectar con el servicio de IA."
    if "neo4j" in type(exc).__module__.lower():
        return 503, "No se pudo conectar con la base de datos."
    return 500, "Ocurrió un error interno procesando la consulta."


def _error_estado_publico(error: Any) -> str | None:
    """Expone solo rechazos de entrada accionables en el panel del cliente."""
    texto = str(error or "")
    if not texto:
        return None
    if texto.startswith(("Pregunta demasiado larga", "La pregunta contiene patrones")):
        return texto
    return "La consulta no pudo completarse de forma segura."


@app.get("/health")
def health() -> dict[str, Any]:
    """Comprueba conectividad real sin ejecutar consultas de datos."""
    try:
        obtener_driver().verify_connectivity()
    except Exception as exc:
        log_paso("api", "health_error", data={"tipo": type(exc).__name__}, nivel="error")
        raise HTTPException(status_code=503, detail="Neo4j no está disponible.") from exc
    return {"ok": True, "servicio": "ciar-agente", "neo4j": "conectado"}


@app.post("/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    """Ejecuta un turno y devuelve respuesta, depuración de lectura y ruta recorrida."""
    pregunta, sesion = body.pregunta.strip(), body.id_sesion.strip()
    segura, motivo = validar_entrada(pregunta)
    if not segura:
        raise HTTPException(status_code=400, detail=motivo)

    config = {"configurable": {"thread_id": sesion}, "recursion_limit": 20}
    pasos: list[str] = [] #Para ver que decisiones esta tomando el agente
    estado_final: dict[str, Any] = {}
    depuracion: dict[str, Any] = {"cypher": None, "entidades": [], "filas": [], "error": None}
    try:
        for paso in grafo.stream(
            {"pregunta": pregunta, "id_sesion": sesion},
            config=config,
            stream_mode="updates",
        ):
            for nombre_nodo, cambios in paso.items():
                pasos.append(nombre_nodo)
                if not cambios:
                    continue
                # Se conserva la última versión no vacía para el panel de depuración del frontend.
                for campo in depuracion:
                    if cambios.get(campo) not in (None, [], ""):
                        depuracion[campo] = cambios[campo]
                estado_final.update(cambios)
    except Exception as exc:
        codigo, detalle = _error_externo(exc)
        log_paso(
            "api",
            "chat_error",
            sesion,
            {"tipo": type(exc).__name__, "error": str(exc)[:200]},
            "error",
        )
        raise HTTPException(status_code=codigo, detail=detalle) from exc

    respuesta = str(estado_final.get("respuesta", "(sin respuesta)"))
    log_fin_turno(sesion, respuesta, pasos)

    return {
        "respuesta": _json_safe(respuesta),
        "cypher": _json_safe(depuracion["cypher"]),
        "entidades": _json_safe(depuracion["entidades"]),
        "filas": _json_safe(depuracion["filas"]),
        "pasos": pasos,
        "error": _json_safe(_error_estado_publico(depuracion["error"])),
    }
