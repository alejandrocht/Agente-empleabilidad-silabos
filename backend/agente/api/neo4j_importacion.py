"""Endpoints explícitos para publicar CSV curriculares en Neo4j."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agente.db.neo4j_importador import ImportacionNeo4jError, importador_neo4j
from agente.normalizador.ejecuciones import gestor_ejecuciones
from agente.normalizador.empleabilidad.neo4j import (
    ImportacionEmpleabilidadError,
    importador_empleabilidad_neo4j,
)
from agente.observabilidad.logger import log_paso
from agente.utils.neo4j_schema import (
    Neo4jSchemaMismatchError,
    get_cached_neo4j_schema,
)

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


class EstadoNeo4jOut(BaseModel):
    """Safe read-only status of the Neo4j dependency used by CIAR."""

    state: Literal["connected", "schema_mismatch", "disconnected"]
    checked_at: str
    latency_ms: float
    missing_labels: list[str] | None = None


def _ejecutar(nombre: str, operacion: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operacion()
    except ImportacionNeo4jError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.mensaje) from exc
    except ImportacionEmpleabilidadError as exc:
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


def _importador_para_ejecucion(id_ejecucion: str) -> Any:
    """Selecciona el importador según el tipo de normalización ya completada."""

    try:
        estado = gestor_ejecuciones.obtener(id_ejecucion)
    except KeyError:
        # Compatibilidad con ejecuciones curriculares de procesos ya reiniciados
        # y con el adaptador de pruebas del importador histórico.
        return importador_neo4j
    return (
        importador_empleabilidad_neo4j
        if estado.get("tipo") == "empleabilidad"
        else importador_neo4j
    )


def _estado_neo4j(
    state: Literal["connected", "schema_mismatch", "disconnected"],
    started_at: float,
    *,
    missing_labels: list[str] | None = None,
) -> EstadoNeo4jOut:
    return EstadoNeo4jOut(
        state=state,
        checked_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        latency_ms=round((perf_counter() - started_at) * 1000, 2),
        missing_labels=missing_labels,
    )


@router.get("/estado", response_model=EstadoNeo4jOut, response_model_exclude_none=True)
def obtener_estado_neo4j() -> EstadoNeo4jOut:
    """Verify the live CIAR schema without exposing Neo4j configuration or secrets."""
    started_at = perf_counter()
    try:
        get_cached_neo4j_schema()
    except Neo4jSchemaMismatchError as exc:
        return _estado_neo4j(
            "schema_mismatch",
            started_at,
            missing_labels=list(exc.missing_labels),
        )
    except Exception as exc:
        log_paso(
            "api.neo4j_importacion",
            "estado_no_disponible",
            data={"tipo": type(exc).__name__},
            nivel="warning",
        )
        return _estado_neo4j("disconnected", started_at)
    return _estado_neo4j("connected", started_at)


@router.post("/validar")
def validar_importacion(body: ValidarImportacionIn) -> dict[str, Any]:
    """Valida el formato, referencias, duplicados y novedad sin escribir."""

    return _ejecutar(
        "validar",
        lambda: _importador_para_ejecucion(body.id_ejecucion).previsualizar(body.id_ejecucion),
    )


@router.post("/importar")
def importar_a_neo4j(body: ImportarNeo4jIn) -> dict[str, Any]:
    """Escribe solo después de que el frontend envía confirmación explícita."""

    return _ejecutar(
        "importar",
        lambda: _importador_para_ejecucion(body.id_ejecucion).importar(
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
