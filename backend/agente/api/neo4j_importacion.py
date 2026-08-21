"""Endpoints explícitos para publicar CSV curriculares en Neo4j."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agente.db.neo4j_importador import ImportacionNeo4jError, importador_neo4j
from agente.observabilidad.logger import log_paso

router = APIRouter()


class ValidarImportacionIn(BaseModel):
    """Identifica la ejecución curricular que se quiere revisar."""

    id_ejecucion: str = Field(..., min_length=20, max_length=20)


class ImportarNeo4jIn(BaseModel):
    """Fingerprint y confirmación de la previsualización mostrada al usuario."""

    id_ejecucion: str = Field(..., min_length=20, max_length=20)
    fingerprint: str = Field(..., min_length=64, max_length=64)
    confirmar: bool = False


class ConfirmarIn(BaseModel):
    """Evita que una reversión ocurra sin una acción explícita del usuario."""

    confirmar: bool = False


def _ejecutar(nombre: str, operacion: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operacion()
    except ImportacionNeo4jError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.mensaje) from exc
    except Exception as exc:
        log_paso(
            "api.neo4j_importacion",
            "operacion_error",
            data={"operacion": nombre, "tipo": type(exc).__name__},
            nivel="error",
        )
        if "neo4j" in type(exc).__module__.lower():
            raise HTTPException(
                status_code=503,
                detail="No se pudo conectar con la base de datos para completar la operación.",
            ) from exc
        raise HTTPException(
            status_code=500,
            detail="La operación de importación no pudo completarse.",
        ) from exc


@router.post("/validar")
def validar_importacion(body: ValidarImportacionIn) -> dict[str, Any]:
    """Valida el formato, referencias, duplicados y novedad sin escribir."""

    return _ejecutar("validar", lambda: importador_neo4j.previsualizar(body.id_ejecucion))


@router.post("/importar")
def importar_a_neo4j(body: ImportarNeo4jIn) -> dict[str, Any]:
    """Escribe solo después de que el frontend envía confirmación explícita."""

    return _ejecutar(
        "importar",
        lambda: importador_neo4j.importar(
            body.id_ejecucion,
            body.fingerprint,
            body.confirmar,
        ),
    )


@router.get("/importaciones")
def listar_importaciones() -> dict[str, Any]:
    """Lista el historial local necesario para ofrecer reversión inmediata."""

    return _ejecutar("historial", lambda: {"importaciones": importador_neo4j.historial()})


@router.post("/importaciones/{id_importacion}/revertir")
def revertir_importacion(id_importacion: str, body: ConfirmarIn) -> dict[str, Any]:
    """Revierte una importación concreta y conserva lo que no creó ese lote."""

    return _ejecutar(
        "revertir",
        lambda: importador_neo4j.revertir(id_importacion, body.confirmar),
    )
