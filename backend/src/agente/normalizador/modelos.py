"""Modelos pequeños y serializables para las ejecuciones del normalizador."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

TipoHoja = Literal["convenios", "informes", "publicaciones"]
Severidad = Literal["error", "warning"]
EstadoEjecucion = Literal[
    "recibido",
    "validando",
    "validado",
    "validado_con_advertencias",
    "limpiando",
    "limpiado",
    "limpiado_con_advertencias",
    "normalizando",
    "normalizado",
    "normalizado_con_advertencias",
    "no_publicado",
    "rechazado",
    "error",
]


@dataclass(frozen=True, slots=True)
class Hallazgo:
    """Describe un problema accionable sin exponer la ruta local del servidor."""

    codigo: str
    severidad: Severidad
    mensaje: str
    hoja: str | None = None
    fila: int | None = None
    campo: str | None = None
    detalle: str | None = None

    def a_dict(self) -> dict[str, object]:
        """Convierte el hallazgo al contrato JSON consumible por el frontend."""

        return {
            "codigo": self.codigo,
            "severidad": self.severidad,
            "mensaje": self.mensaje,
            "hoja": self.hoja,
            "fila": self.fila,
            "campo": self.campo,
            "detalle": self.detalle,
        }


@dataclass(frozen=True, slots=True)
class HojaInspeccion:
    """Resumen estructural de una hoja fuente identificada por su función."""

    nombre: str
    rol: TipoHoja | None
    anios: tuple[int, ...]
    encabezado_fila: int | None
    filas_datos: int
    columnas: tuple[str, ...]

    def a_dict(self) -> dict[str, object]:
        """Convierte la inspección a JSON sin perder el nombre original de la hoja."""

        return {
            "nombre": self.nombre,
            "rol": self.rol,
            "anios": list(self.anios),
            "encabezado_fila": self.encabezado_fila,
            "filas_datos": self.filas_datos,
            "columnas": list(self.columnas),
        }


@dataclass(frozen=True, slots=True)
class ResultadoValidacionEntrada:
    """Resultado completo del gate de entrada del normalizador laboral."""

    archivo: str
    sha256: str
    valida: bool
    hojas: tuple[HojaInspeccion, ...]
    hallazgos: tuple[Hallazgo, ...]

    def a_dict(self) -> dict[str, object]:
        """Convierte la validación al contrato público de la ejecución."""

        return {
            "archivo": self.archivo,
            "sha256": self.sha256,
            "valida": self.valida,
            "hojas": [hoja.a_dict() for hoja in self.hojas],
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
        }


@dataclass(frozen=True, slots=True)
class ResultadoLimpieza:
    """Resumen de los archivos JSONL de staging generados desde la fuente."""

    registros_por_universo: dict[str, int]
    outputs: tuple[dict[str, object], ...]
    hallazgos: tuple[Hallazgo, ...]

    def a_dict(self) -> dict[str, object]:
        """Convierte el resultado de limpieza al contrato de la ejecución."""

        return {
            "registros_por_universo": dict(self.registros_por_universo),
            "outputs": list(self.outputs),
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
        }


@dataclass(frozen=True, slots=True)
class ResultadoNormalizacion:
    """Resultado de la extracción CHH antes de publicar el paquete."""

    publicable: bool
    registros_procesados: dict[str, int]
    relaciones: int
    cuarentena: int
    outputs: tuple[dict[str, object], ...]
    hallazgos: tuple[Hallazgo, ...]

    def a_dict(self) -> dict[str, object]:
        """Convierte el gate semántico al manifest de ejecución."""

        return {
            "publicable": self.publicable,
            "registros_procesados": dict(self.registros_procesados),
            "relaciones": self.relaciones,
            "cuarentena": self.cuarentena,
            "outputs": list(self.outputs),
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
        }


@dataclass(frozen=True, slots=True)
class ArchivoSilabo:
    """Archivo curricular aceptado dentro del paquete de una carrera."""

    nombre: str
    formato: Literal["docx", "pdf"]
    bytes: int

    def a_dict(self) -> dict[str, object]:
        return {"nombre": self.nombre, "formato": self.formato, "bytes": self.bytes}


@dataclass(frozen=True, slots=True)
class ResultadoValidacionSilabos:
    """Resultado del contrato de carrera, periodo y archivos curriculares."""

    archivo: str
    carrera: str
    periodo: str
    sha256: str
    valida: bool
    archivos: tuple[ArchivoSilabo, ...]
    hallazgos: tuple[Hallazgo, ...]

    def a_dict(self) -> dict[str, object]:
        return {
            "archivo": self.archivo,
            "carrera": self.carrera,
            "periodo": self.periodo,
            "sha256": self.sha256,
            "valida": self.valida,
            "archivos": [archivo.a_dict() for archivo in self.archivos],
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
        }


FaseProgresoLLM = Literal[
    "preparando",
    "extrayendo",
    "analista",
    "analista_residual",
    "inspector",
    "inspector_residual",
    "finalizando",
    "completado",
    "error",
]
EstadoReporteFinalLLM = Literal["pendiente", "disponible", "error"]


@dataclass(frozen=True, slots=True)
class UltimoChunkLimpiezaLLM:
    """Resumen del último lote LLM terminado, sin datos curriculares sensibles."""

    fase: FaseProgresoLLM
    logros: int
    silabos: int

    def a_dict(self) -> dict[str, object]:
        return {
            "fase": self.fase,
            "logros": self.logros,
            "silabos": self.silabos,
        }


@dataclass(frozen=True, slots=True)
class EventoProgresoLimpiezaLLM:
    """Hito serializable de la limpieza, limitado por el snapshot público."""

    secuencia: int
    timestamp: str
    fase: FaseProgresoLLM
    mensaje: str
    chunks_completados: int
    chunks_totales: int
    logros_chunk: int
    silabos_chunk: int
    logros_detectados: int
    logros_procesados: int
    logros_totales: int
    silabos_detectados: int
    silabos_procesados: int
    silabos_totales: int
    decisiones_cacheadas: int
    reintentos: int

    def a_dict(self) -> dict[str, object]:
        return {
            "secuencia": self.secuencia,
            "timestamp": self.timestamp,
            "fase": self.fase,
            "mensaje": self.mensaje,
            "chunks_completados": self.chunks_completados,
            "chunks_totales": self.chunks_totales,
            "logros_chunk": self.logros_chunk,
            "silabos_chunk": self.silabos_chunk,
            "logros_detectados": self.logros_detectados,
            "logros_procesados": self.logros_procesados,
            "logros_totales": self.logros_totales,
            "silabos_detectados": self.silabos_detectados,
            "silabos_procesados": self.silabos_procesados,
            "silabos_totales": self.silabos_totales,
            "decisiones_cacheadas": self.decisiones_cacheadas,
            "reintentos": self.reintentos,
        }


@dataclass(frozen=True, slots=True)
class ProgresoLimpiezaLLM:
    """Contrato incremental publicado mientras corre la limpieza curricular LLM."""

    fase: FaseProgresoLLM
    chunks_completados: int
    chunks_totales: int
    logros_procesados: int
    logros_totales: int
    silabos_procesados: int
    silabos_totales: int
    decisiones_cacheadas: int
    reintentos: int
    silabos_detectados: int = 0
    logros_detectados: int = 0
    mensaje: str = ""
    ultimo_chunk: UltimoChunkLimpiezaLLM | None = None
    reporte_final: EstadoReporteFinalLLM = "pendiente"
    eventos: tuple[EventoProgresoLimpiezaLLM, ...] = ()

    def con_evento(
        self,
        mensaje: str,
        *,
        logros_chunk: int = 0,
        silabos_chunk: int = 0,
    ) -> ProgresoLimpiezaLLM:
        """Devuelve un snapshot con un hito nuevo y conserva solo los últimos 100."""

        eventos_previos = self.eventos[-100:]
        secuencia = eventos_previos[-1].secuencia + 1 if eventos_previos else 1
        evento = EventoProgresoLimpiezaLLM(
            secuencia=secuencia,
            timestamp=datetime.now(UTC).isoformat(),
            fase=self.fase,
            mensaje=mensaje,
            chunks_completados=self.chunks_completados,
            chunks_totales=self.chunks_totales,
            logros_chunk=logros_chunk,
            silabos_chunk=silabos_chunk,
            logros_detectados=self.logros_detectados,
            logros_procesados=self.logros_procesados,
            logros_totales=self.logros_totales,
            silabos_detectados=self.silabos_detectados,
            silabos_procesados=self.silabos_procesados,
            silabos_totales=self.silabos_totales,
            decisiones_cacheadas=self.decisiones_cacheadas,
            reintentos=self.reintentos,
        )
        return replace(self, mensaje=mensaje, eventos=(*eventos_previos, evento)[-100:])

    def a_dict(self) -> dict[str, object]:
        return {
            "fase": self.fase,
            "chunks_completados": self.chunks_completados,
            "chunks_totales": self.chunks_totales,
            "logros_procesados": self.logros_procesados,
            "logros_totales": self.logros_totales,
            "silabos_procesados": self.silabos_procesados,
            "silabos_totales": self.silabos_totales,
            "decisiones_cacheadas": self.decisiones_cacheadas,
            "reintentos": self.reintentos,
            "logros_detectados": self.logros_detectados,
            "mensaje": self.mensaje,
            "silabos_detectados": self.silabos_detectados,
            "ultimo_chunk": self.ultimo_chunk.a_dict() if self.ultimo_chunk else None,
            "reporte_final": self.reporte_final,
            "eventos": [evento.a_dict() for evento in self.eventos[-100:]],
        }


@dataclass(frozen=True, slots=True)
class ResultadoLimpiezaSilabos:
    """Resumen de los CSV curriculares generados desde DOCX/PDF."""

    registros: int
    outputs: tuple[dict[str, object], ...]
    hallazgos: tuple[Hallazgo, ...]
    publicable: bool = False
    relaciones: int = 0
    competencias: int = 0
    habilidades: int = 0
    herramientas: int = 0

    def a_dict(self) -> dict[str, object]:
        return {
            "registros": self.registros,
            "publicable": self.publicable,
            "relaciones": self.relaciones,
            "competencias": self.competencias,
            "habilidades": self.habilidades,
            "herramientas": self.herramientas,
            "outputs": list(self.outputs),
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
        }
