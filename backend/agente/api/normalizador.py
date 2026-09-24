"""Endpoints de ejecución del normalizador, separados del chat de solo lectura."""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
from collections.abc import Callable, Coroutine
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr

from agente.config.settings import entero
from agente.normalizador.ejecuciones import (
    EjecucionNoCancelable,
    HistorialNoEliminable,
    gestor_ejecuciones,
)
from agente.normalizador.modelos import Hallazgo
from agente.observabilidad.logger import log_paso

aprobaciones_tecnicas = import_module("agente.normalizador.silabos.aprobaciones_tecnicas")
errores_tecnicos = import_module("agente.normalizador.silabos.errores_tecnicos")


MAX_UPLOAD_BYTES = entero("NORMALIZADOR_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)
_UPLOAD_PATHS = frozenset({"/normalizador/silabos"})
_GENERIC_UPLOAD_LIMIT_DETAIL = "La carga excede el límite permitido."


def _content_length_exceeds_limit(value: str | None) -> bool:
    """Return whether a valid decimal Content-Length proves an oversized request."""

    if value is None or not value.isascii() or not value.isdecimal():
        return False
    try:
        return int(value) > MAX_UPLOAD_BYTES
    except ValueError:
        return False


class _EarlyUploadLimitRoute(APIRoute):
    """Reject proven oversized multipart requests before FastAPI parses their body."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if request.url.path in _UPLOAD_PATHS and _content_length_exceeds_limit(
                request.headers.get("content-length")
            ):
                return JSONResponse(
                    status_code=413,
                    content={"detail": _GENERIC_UPLOAD_LIMIT_DETAIL},
                )
            return await handler(request)

        return handle


router = APIRouter(route_class=_EarlyUploadLimitRoute)


class DecisionCurricularIn(BaseModel):
    """Decisión explícita sobre una propuesta no catalogada."""

    id_pendiente: str | None = Field(default=None, min_length=1, max_length=200)
    decision: Literal["ADD", "KEEP_PENDING", "DISCARD"]
    reason: str | None = Field(default=None, min_length=1, max_length=600)


class DecidirPendientesIn(BaseModel):
    """Lote atómico de decisiones del ejecutor de la normalización."""

    decisiones: list[DecisionCurricularIn] = Field(default_factory=list, max_length=1000)
    actor: str = Field(default="ejecutor", min_length=1, max_length=200)
    revision: str | None = Field(default=None, min_length=1, max_length=64)


class IniciarSilabosCactusIn(BaseModel):
    """Solicitud para extraer sílabos desde Cactus sin guardar credenciales."""

    carrera: str = Field(..., min_length=1, max_length=200)
    periodo: str = Field(..., min_length=1, max_length=20)
    usuario: str = Field(..., min_length=1, max_length=200)
    hitl: Literal[0, 1] = Field(default=1)
    # La longitud se valida en la ruta para que los errores de Pydantic no hagan
    # eco de una contraseña enviada en el campo `input` de la respuesta 422.
    contrasena: SecretStr


class EventoHitlIn(BaseModel):
    """Cambio explícito del modo HITL, independiente de una ejecución."""

    hitl: Literal[0, 1]


@router.post("/eventos/hitl", status_code=204)
def registrar_evento_hitl(solicitud: EventoHitlIn) -> Response:
    """Registra el modo HITL seleccionado sin crear ni modificar ejecuciones."""

    modo = "aprobacion_automatica" if solicitud.hitl == 0 else "revision_humana"
    log_paso(
        "normalizador",
        "hitl_cambiado",
        data={"hitl": str(solicitud.hitl), "modo": modo},
    )
    return Response(status_code=204)


@router.post("/silabos", status_code=202)
def iniciar_silabos(
    archivo: UploadFile = File(...),
    carrera: str = Form(..., min_length=1, max_length=200),
    periodo: str = Form(..., min_length=1, max_length=20),
    hitl: int = Form(default=1, ge=0, le=1),
) -> dict[str, object]:
    """Recibe un ZIP, DOCX o PDF curricular junto con carrera y periodo declarados."""

    nombre = Path(archivo.filename or "entrada.zip").name or "entrada.zip"
    parametros = {
        "carrera": carrera.strip(),
        "periodo": periodo.strip(),
        "hitl": str(hitl),
    }
    id_ejecucion, directorio = gestor_ejecuciones.crear("silabos", nombre, parametros)
    ruta_entrada = directorio / "entrada" / nombre
    try:
        with ruta_entrada.open("wb") as destino:
            shutil.copyfileobj(archivo.file, destino, length=1024 * 1024)
    finally:
        archivo.file.close()

    tamano = ruta_entrada.stat().st_size
    if tamano > MAX_UPLOAD_BYTES:
        gestor_ejecuciones.marcar_rechazo(
            id_ejecucion,
            Hallazgo(
                codigo="ARCHIVO_DEMASIADO_GRANDE",
                severidad="error",
                mensaje="El archivo supera el límite permitido.",
                detalle=f"bytes={tamano}; máximo={MAX_UPLOAD_BYTES}",
            ),
        )
        return gestor_ejecuciones.obtener(id_ejecucion)

    gestor_ejecuciones.iniciar_validacion_silabos(
        id_ejecucion,
        ruta_entrada,
        parametros["carrera"],
        parametros["periodo"],
    )
    return gestor_ejecuciones.obtener(id_ejecucion)


@router.post("/silabos/cactus", status_code=202)
def iniciar_silabos_cactus(solicitud: IniciarSilabosCactusIn) -> dict[str, object]:
    """Extrae una carrera/periodo desde Cactus y ejecuta el pipeline curricular."""

    carrera = solicitud.carrera.strip()
    periodo = solicitud.periodo.strip()
    contrasena = solicitud.contrasena.get_secret_value()
    if not contrasena or len(contrasena) > 200:
        raise HTTPException(
            status_code=422,
            detail="La contraseña de ULima debe tener entre 1 y 200 caracteres.",
        )
    nombre = "cactus.zip"
    parametros = {
        "carrera": carrera,
        "periodo": periodo,
        "fuente": "cactus",
        "hitl": str(solicitud.hitl),
    }
    id_ejecucion, _directorio = gestor_ejecuciones.crear("silabos", nombre, parametros)
    gestor_ejecuciones.iniciar_extraccion_silabos(
        id_ejecucion,
        carrera,
        periodo,
        solicitud.usuario.strip(),
        contrasena,
    )
    return gestor_ejecuciones.obtener(id_ejecucion)


@router.get("/ejecuciones/{id_ejecucion}/errores")
def errores_ejecucion(id_ejecucion: str) -> dict[str, object]:
    """Entrega solo los hallazgos para que el frontend pueda mostrarlos con detalle."""

    try:
        estado = gestor_ejecuciones.obtener(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc
    return {
        "id_ejecucion": id_ejecucion,
        "estado": estado["estado"],
        "hallazgos": estado["hallazgos"],
    }


@router.post("/ejecuciones/{id_ejecucion}/cancelar", status_code=202)
def cancelar_ejecucion(id_ejecucion: str) -> dict[str, object]:
    """Solicita detener la ejecución antes del siguiente lote costoso."""

    if re.fullmatch(r"NOR_[0-9a-f]{16}", id_ejecucion) is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")
    try:
        return gestor_ejecuciones.cancelar(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc
    except EjecucionNoCancelable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/ejecuciones")
def listar_ejecuciones(
    limite: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    """Devuelve el historial compacto con la política TTL/LRU aplicada."""

    return gestor_ejecuciones.listar_historial(limite)


@router.get("/ejecuciones/{id_ejecucion}/reporte")
def descargar_reporte_ejecucion(id_ejecucion: str) -> JSONResponse:
    """Descarga el manifest y los reportes auditables como un único JSON."""

    if re.fullmatch(r"NOR_[0-9a-f]{16}", id_ejecucion) is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")
    try:
        reporte = gestor_ejecuciones.obtener_reporte(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc
    return JSONResponse(
        content=reporte,
        headers={
            "Content-Disposition": f'attachment; filename="{id_ejecucion}_reporte.json"',
        },
    )


@router.delete("/ejecuciones/{id_ejecucion}/historial")
def eliminar_ejecucion_historial(id_ejecucion: str) -> dict[str, object]:
    """Elimina manualmente una carpeta terminal del historial."""

    if re.fullmatch(r"NOR_[0-9a-f]{16}", id_ejecucion) is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")
    try:
        return gestor_ejecuciones.eliminar_historial(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc
    except HistorialNoEliminable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/ejecuciones/{id_ejecucion}")
def obtener_ejecucion(id_ejecucion: str) -> dict[str, object]:
    """Consulta el estado, validación y outputs de una ejecución."""

    try:
        return gestor_ejecuciones.obtener(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc


@router.get("/ejecuciones/{id_ejecucion}/outputs/{ruta_salida:path}")
def descargar_output(id_ejecucion: str, ruta_salida: str) -> FileResponse:
    """Descarga un output declarado por la ejecución, sin exponer rutas internas."""

    if re.fullmatch(r"NOR_[0-9a-f]{16}", id_ejecucion) is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")

    try:
        ejecucion = gestor_ejecuciones.obtener(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc

    relativa = Path(ruta_salida)
    if not ruta_salida or "\x00" in ruta_salida or relativa.is_absolute() or ".." in relativa.parts:
        raise HTTPException(status_code=404, detail="Output no encontrado.")

    salidas = ejecucion.get("outputs")
    permitidos: set[str] = set()
    if isinstance(salidas, list):
        for salida in salidas:
            if isinstance(salida, dict) and isinstance(salida.get("archivo"), str):
                permitidos.add(Path(salida["archivo"]).as_posix())

    ruta_normalizada = relativa.as_posix()
    if ruta_normalizada not in permitidos:
        raise HTTPException(status_code=404, detail="Output no encontrado.")

    raiz = (gestor_ejecuciones.base_dir / id_ejecucion).resolve()
    candidatas = [raiz / relativa]
    ruta = next(
        (
            candidata.resolve()
            for candidata in candidatas
            if raiz in candidata.resolve().parents and candidata.is_file()
        ),
        None,
    )
    if ruta is None:
        raise HTTPException(status_code=404, detail="Output no encontrado.")

    tipo, _ = mimetypes.guess_type(ruta.name)
    return FileResponse(
        path=ruta,
        filename=ruta.name,
        media_type=tipo or "application/octet-stream",
    )


@router.get("/ejecuciones/{id_ejecucion}/cuarentena")
def cuarentena_ejecucion(
    id_ejecucion: str,
    desde: int = Query(default=0, ge=0),
    limite: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    """Devuelve una ventana de filas no publicables con su contexto de origen."""

    try:
        gestor_ejecuciones.obtener(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc
    if re.fullmatch(r"NOR_[0-9a-f]{16}", id_ejecucion) is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")

    ruta = gestor_ejecuciones.base_dir / id_ejecucion / "salidas" / "reportes" / "cuarentena.jsonl"
    if not ruta.is_file():
        return {
            "id_ejecucion": id_ejecucion,
            "total": 0,
            "desde": desde,
            "limite": limite,
            "filas": [],
        }

    filas: list[object] = []
    total = 0
    with ruta.open("r", encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            if desde <= total < desde + limite:
                try:
                    filas.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
            total += 1
    return {
        "id_ejecucion": id_ejecucion,
        "total": total,
        "desde": desde,
        "limite": limite,
        "filas": filas,
    }


@router.get("/ejecuciones/{id_ejecucion}/pendientes")
def pendientes_ejecucion(
    id_ejecucion: str,
    desde: int = Query(default=0, ge=0),
    limite: int = Query(default=50, ge=1, le=200),
    incluir_resueltas: bool = Query(default=True),
) -> dict[str, object]:
    """Devuelve la cola curricular explícita sin ocultar propuestas no catalogadas."""

    estado = _exigir_ejecucion_normalizador(id_ejecucion)
    if estado.get("tipo") != "silabos":
        raise HTTPException(
            status_code=409,
            detail="Las propuestas técnicas solo aplican a ejecuciones de sílabos.",
        )
    try:
        return cast(
            dict[str, object],
            aprobaciones_tecnicas.pendientes_para_api(
                gestor_ejecuciones.base_dir / id_ejecucion,
                desde=desde,
                limite=limite,
                incluir_resueltas=incluir_resueltas,
            ),
        )
    except errores_tecnicos.AprobacionNoPermitida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except errores_tecnicos.DecisionCurricularInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/ejecuciones/{id_ejecucion}/pendientes/decidir")
def decidir_pendientes_ejecucion(
    id_ejecucion: str,
    solicitud: DecidirPendientesIn,
) -> dict[str, object]:
    """Promueve o mantiene pendientes sin bloquear el worker curricular."""

    estado = _exigir_ejecucion_normalizador(id_ejecucion)
    if estado.get("tipo") != "silabos":
        raise HTTPException(
            status_code=409,
            detail="Las decisiones técnicas solo aplican a ejecuciones de sílabos.",
        )
    try:
        resultado = aprobaciones_tecnicas.aplicar_decisiones(
            gestor_ejecuciones.base_dir / id_ejecucion,
            [decision.model_dump() for decision in solicitud.decisiones],
            actor=solicitud.actor,
            revision=solicitud.revision,
        )
    except errores_tecnicos.AprobacionNoPermitida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except errores_tecnicos.RevisionCurricularInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except errores_tecnicos.DecisionCurricularInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id_ejecucion": id_ejecucion,
        "estado": estado.get("estado"),
        **resultado,
    }


@router.get("/ejecuciones/{id_ejecucion}/release-gate")
def release_gate_ejecucion(id_ejecucion: str) -> dict[str, object]:
    """Expone la decisión de publicación y sus bloqueadores auditables."""

    estado = _exigir_ejecucion_normalizador(id_ejecucion)
    gate = estado.get("release_gate")
    if not isinstance(gate, dict):
        limpieza = estado.get("limpieza_silabos")
        if isinstance(limpieza, dict):
            gate = limpieza.get("release_gate")
    if not isinstance(gate, dict):
        ruta = (
            gestor_ejecuciones.base_dir
            / id_ejecucion
            / "salidas"
            / "reportes"
            / "release_gate.json"
        )
        if ruta.is_file():
            try:
                contenido = json.loads(ruta.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                contenido = None
            if isinstance(contenido, dict):
                gate = contenido
    return {
        "id_ejecucion": id_ejecucion,
        "estado": estado.get("estado"),
        "release_gate": gate if isinstance(gate, dict) else None,
    }


def _exigir_ejecucion_normalizador(id_ejecucion: str) -> dict[str, object]:
    if re.fullmatch(r"NOR_[0-9a-f]{16}", id_ejecucion) is None:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.")
    try:
        return gestor_ejecuciones.obtener(id_ejecucion)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Ejecución no encontrada.") from exc


def _leer_ventana_jsonl(
    ruta: Path,
    desde: int,
    limite: int,
) -> tuple[list[object], int]:
    if not ruta.is_file():
        return [], 0
    filas: list[object] = []
    total = 0
    with ruta.open("r", encoding="utf-8") as archivo:
        for linea in archivo:
            if not linea.strip():
                continue
            if desde <= total < desde + limite:
                try:
                    filas.append(json.loads(linea))
                except json.JSONDecodeError:
                    continue
            total += 1
    return filas, total
