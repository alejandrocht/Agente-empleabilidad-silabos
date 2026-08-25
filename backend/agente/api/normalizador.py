"""Endpoints de ejecución del normalizador, separados del chat de solo lectura."""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from agente.config.settings import entero
from agente.normalizador.ejecuciones import (
    EjecucionNoCancelable,
    HistorialNoEliminable,
    gestor_ejecuciones,
)
from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos import aprobaciones

router = APIRouter()
MAX_UPLOAD_BYTES = entero("NORMALIZADOR_MAX_UPLOAD_BYTES", 100 * 1024 * 1024)


class DecisionCurricularIn(BaseModel):
    """Decisión explícita sobre una propuesta no catalogada."""

    id_pendiente: str = Field(..., min_length=1, max_length=200)
    decision: Literal["ADD", "KEEP_PENDING"]


class DecidirPendientesIn(BaseModel):
    """Lote atómico de decisiones del ejecutor de la normalización."""

    decisiones: list[DecisionCurricularIn] = Field(..., min_length=1, max_length=1000)
    actor: str = Field(default="ejecutor", min_length=1, max_length=200)


@router.post("/empleabilidad", status_code=202)
def iniciar_empleabilidad(archivo: UploadFile = File(...)) -> dict[str, object]:
    """Recibe el XLSX y devuelve un ID para consultar el progreso."""

    nombre = Path(archivo.filename or "entrada.xlsx").name
    id_ejecucion, directorio = gestor_ejecuciones.crear("empleabilidad", nombre)
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

    gestor_ejecuciones.iniciar_validacion(id_ejecucion, ruta_entrada)
    return gestor_ejecuciones.obtener(id_ejecucion)


@router.post("/silabos", status_code=202)
def iniciar_silabos(
    archivo: UploadFile = File(...),
    carrera: str = Form(..., min_length=1, max_length=200),
    periodo: str = Form(..., min_length=1, max_length=20),
) -> dict[str, object]:
    """Recibe un ZIP, DOCX o PDF curricular junto con carrera y periodo declarados."""

    nombre = Path(archivo.filename or "entrada.zip").name or "entrada.zip"
    parametros = {"carrera": carrera.strip(), "periodo": periodo.strip()}
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
    # Compatibilidad con manifests antiguos de empleabilidad que solo guardaban
    # el nombre del archivo y materializaban todos los outputs bajo `salidas/`.
    if len(relativa.parts) == 1:
        candidatas.append(raiz / "salidas" / relativa)
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
                filas.append(json.loads(linea))
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

    _exigir_ejecucion_normalizador(id_ejecucion)
    ruta = (
        gestor_ejecuciones.base_dir
        / id_ejecucion
        / "salidas"
        / "reportes"
        / "pendientes_curriculares.jsonl"
    )
    filas: list[object]
    if incluir_resueltas:
        filas, total = _leer_ventana_jsonl(ruta, desde, limite)
    else:
        todas = aprobaciones.pendientes_para_revision(gestor_ejecuciones.base_dir / id_ejecucion)
        total = len(todas)
        filas = []
        filas.extend(todas[desde : desde + limite])
    return {
        "id_ejecucion": id_ejecucion,
        "total": total,
        "desde": desde,
        "limite": limite,
        "filas": filas,
        "aprobacion": aprobaciones.resumen_aprobacion_curricular(
            gestor_ejecuciones.base_dir / id_ejecucion
        ),
    }


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
            detail="Las decisiones curriculares solo aplican a ejecuciones de sílabos.",
        )
    try:
        resultado = aprobaciones.aplicar_decisiones_curriculares(
            gestor_ejecuciones.base_dir / id_ejecucion,
            [decision.model_dump() for decision in solicitud.decisiones],
            actor=solicitud.actor,
        )
    except aprobaciones.AprobacionNoPermitida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except aprobaciones.DecisionCurricularInvalida as exc:
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
                filas.append(json.loads(linea))
            total += 1
    return filas, total
