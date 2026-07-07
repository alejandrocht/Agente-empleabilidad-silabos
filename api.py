"""
api.py - puente HTTP minimo para la demo web del agente CIAR.

No duplica la logica del agente: construye el grafo una vez y ejecuta el mismo
stream que usa main.py, exponiendo solo el estado necesario para el frontend.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import construir_grafo
from utils.config import cargar_entorno
from utils.neo4j import obtener_driver

cargar_entorno()
grafo = construir_grafo()

app = FastAPI(title="CIAR Agente API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ChatIn(BaseModel):
    pregunta: str = Field(..., min_length=1)
    id_sesion: str = Field(..., min_length=1)


def _json_safe(valor: Any) -> Any:
    """Convierte tipos de Neo4j/LangChain a estructuras JSON simples."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, dict):
        return {str(k): _json_safe(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [_json_safe(v) for v in valor]
    return str(valor)


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        obtener_driver().verify_connectivity()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "servicio": "ciar-agente", "neo4j": "conectado"}


@app.post("/chat")
def chat(body: ChatIn) -> dict[str, Any]:
    pregunta = body.pregunta.strip()
    id_sesion = body.id_sesion.strip()
    if not pregunta:
        raise HTTPException(status_code=422, detail="La pregunta no puede estar vacia.")

    config = {
        "configurable": {"thread_id": id_sesion},
        "recursion_limit": 15,
    }
    entrada = {"pregunta": pregunta, "id_sesion": id_sesion}

    pasos: list[str] = []
    estado_final: dict[str, Any] = {}
    depuracion: dict[str, Any] = {
        "cypher": None,
        "entidades": [],
        "filas": [],
        "error": None,
    }

    try:
        for paso in grafo.stream(entrada, config=config, stream_mode="updates"):
            for nombre_nodo, cambios in paso.items():
                pasos.append(nombre_nodo)
                if cambios:
                    if cambios.get("cypher"):
                        depuracion["cypher"] = cambios["cypher"]
                    if cambios.get("entidades"):
                        depuracion["entidades"] = cambios["entidades"]
                    if cambios.get("filas"):
                        depuracion["filas"] = cambios["filas"]
                    if cambios.get("error"):
                        depuracion["error"] = cambios["error"]
                    estado_final.update(cambios)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error del agente: {exc}") from exc

    return {
        "respuesta": _json_safe(estado_final.get("respuesta", "(sin respuesta)")),
        "cypher": _json_safe(depuracion["cypher"]),
        "entidades": _json_safe(depuracion["entidades"]),
        "filas": _json_safe(depuracion["filas"]),
        "pasos": pasos,
        "error": _json_safe(depuracion["error"]),
    }
