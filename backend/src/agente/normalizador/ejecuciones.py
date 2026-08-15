"""Ejecuciones en segundo plano para la puerta de entrada del normalizador."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import cast
from uuid import uuid4

from agente.config.settings import BASE_DIR, booleano, texto
from agente.normalizador.empleabilidad.catalogo import (
    cargar_catalogo,
    cargar_catalogo_carrera,
)
from agente.normalizador.empleabilidad.entrada import validar_archivo
from agente.normalizador.empleabilidad.limpieza import limpiar_archivo
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.modelos import (
    EstadoEjecucion,
    Hallazgo,
    ProgresoLimpiezaLLM,
    ResultadoLimpieza,
    ResultadoLimpiezaSilabos,
    ResultadoNormalizacion,
    ResultadoValidacionEntrada,
    ResultadoValidacionSilabos,
)
from agente.normalizador.silabos.entrada import validar_archivo as validar_silabos
from agente.normalizador.silabos.limpieza import limpiar_archivo as limpiar_silabos
from agente.observabilidad.langsmith import contexto_ejecucion, ejecutar_flujo


def _ahora() -> str:
    """Genera timestamps UTC comparables entre procesos y ejecuciones."""

    return datetime.now(UTC).isoformat()


class Ejecucion:
    """Estado mutable mínimo de una ejecución de normalización."""

    def __init__(
        self,
        id_ejecucion: str,
        tipo: str,
        archivo: str,
        directorio: Path,
        parametros: dict[str, str] | None = None,
    ) -> None:
        self.id_ejecucion = id_ejecucion
        self.tipo = tipo
        self.archivo = archivo
        self.directorio = directorio
        self.parametros = parametros or {}
        self.estado: EstadoEjecucion = "recibido"
        self.creada_en = _ahora()
        self.actualizada_en = self.creada_en
        self.validacion: ResultadoValidacionEntrada | None = None
        self.validacion_silabos: ResultadoValidacionSilabos | None = None
        self.limpieza: ResultadoLimpieza | None = None
        self.limpieza_silabos: ResultadoLimpiezaSilabos | None = None
        self.normalizacion: ResultadoNormalizacion | None = None
        self.catalogo_chh: dict[str, object] | None = None
        self.hallazgos: list[Hallazgo] = []
        self.progreso_llm: ProgresoLimpiezaLLM | None = None

    def a_dict(self) -> dict[str, object]:
        """Expone el contrato público sin filtrar rutas internas del servidor."""

        return {
            "id_ejecucion": self.id_ejecucion,
            "tipo": self.tipo,
            "archivo": self.archivo,
            "parametros": dict(self.parametros),
            "estado": self.estado,
            "creada_en": self.creada_en,
            "actualizada_en": self.actualizada_en,
            "validacion": self.validacion.a_dict() if self.validacion else None,
            "validacion_silabos": (
                self.validacion_silabos.a_dict() if self.validacion_silabos else None
            ),
            "limpieza": self.limpieza.a_dict() if self.limpieza else None,
            "limpieza_silabos": (self.limpieza_silabos.a_dict() if self.limpieza_silabos else None),
            "normalizacion": self.normalizacion.a_dict() if self.normalizacion else None,
            "catalogo_chh": self.catalogo_chh,
            "progreso_llm": self.progreso_llm.a_dict() if self.progreso_llm else None,
            "hallazgos": [hallazgo.a_dict() for hallazgo in self.hallazgos],
            "outputs": (
                list(self.normalizacion.outputs)
                if self.normalizacion
                else list(self.limpieza.outputs)
                if self.limpieza
                else list(self.limpieza_silabos.outputs)
                if self.limpieza_silabos
                else []
            ),
        }


class GestorEjecuciones:
    """Coordina validaciones cortas y persiste un manifest por ejecución."""

    def __init__(self, base_dir: Path | None = None) -> None:
        configurado = texto("NORMALIZADOR_DATA_DIR")
        self.base_dir = base_dir or Path(configurado or BASE_DIR / ".normalizador")
        self._ejecuciones: dict[str, Ejecucion] = {}
        self._bloqueo = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="normalizador")

    def crear(
        self,
        tipo: str,
        archivo: str,
        parametros: dict[str, str] | None = None,
    ) -> tuple[str, Path]:
        """Crea el directorio aislado de una ejecución antes de guardar la fuente."""

        id_ejecucion = f"NOR_{uuid4().hex[:16]}"
        directorio = self.base_dir / id_ejecucion
        (directorio / "entrada").mkdir(parents=True, exist_ok=False)
        ejecucion = Ejecucion(id_ejecucion, tipo, archivo, directorio, parametros)
        with self._bloqueo:
            self._ejecuciones[id_ejecucion] = ejecucion
        self._persistir(ejecucion)
        return id_ejecucion, directorio

    def iniciar_validacion(self, id_ejecucion: str, ruta_entrada: Path) -> None:
        """Programa la validación sin bloquear la petición HTTP."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "validando"
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._executor.submit(self._validar, ejecucion, ruta_entrada)

    def iniciar_validacion_silabos(
        self,
        id_ejecucion: str,
        ruta_entrada: Path,
        carrera: str,
        periodo: str,
    ) -> None:
        """Programa la validación y limpieza curricular en segundo plano."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "validando"
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._executor.submit(self._validar_silabos, ejecucion, ruta_entrada, carrera, periodo)

    def marcar_rechazo(self, id_ejecucion: str, hallazgo: Hallazgo) -> None:
        """Marca un rechazo inmediato, por ejemplo por límite de carga."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "rechazado"
        ejecucion.hallazgos = [hallazgo]
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)

    def obtener(self, id_ejecucion: str) -> dict[str, object]:
        """Obtiene el estado serializable de una ejecución activa."""

        try:
            return self._obtener_objeto(id_ejecucion).a_dict()
        except KeyError:
            manifest = self.base_dir / id_ejecucion / "manifest.json"
            if not manifest.exists():
                raise
            datos = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("El manifest de la ejecución no tiene un objeto raíz.")
            return cast(dict[str, object], datos)

    def _obtener_objeto(self, id_ejecucion: str) -> Ejecucion:
        with self._bloqueo:
            ejecucion = self._ejecuciones.get(id_ejecucion)
        if ejecucion is None:
            raise KeyError(id_ejecucion)
        return ejecucion

    def _validar(self, ejecucion: Ejecucion, ruta_entrada: Path) -> None:
        """Ejecuta el gate y genera staging solo cuando la fuente es estructuralmente válida."""

        try:
            resultado = validar_archivo(ruta_entrada, ejecucion.archivo)
        except Exception as exc:
            ejecucion.estado = "error"
            ejecucion.hallazgos = [
                Hallazgo(
                    codigo="ERROR_INTERNO_VALIDACION",
                    severidad="error",
                    mensaje="La validación terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            ]
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            return

        ejecucion.validacion = resultado
        ejecucion.hallazgos = list(resultado.hallazgos)
        if not resultado.valida:
            ejecucion.estado = "rechazado"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            return

        try:
            ejecucion.catalogo_chh = cargar_catalogo().resumen()
        except Exception as exc:
            ejecucion.catalogo_chh = {
                "disponible": False,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            }

        try:
            ejecucion.estado = "limpiando"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            limpieza = limpiar_archivo(ruta_entrada, ejecucion.directorio, resultado)
            ejecucion.limpieza = limpieza
            ejecucion.hallazgos = list(resultado.hallazgos) + list(limpieza.hallazgos)
            ejecucion.estado = (
                "limpiado_con_advertencias"
                if any(hallazgo.severidad == "warning" for hallazgo in ejecucion.hallazgos)
                else "limpiado"
            )
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)

            ejecucion.estado = "normalizando"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            normalizacion = normalizar_staging(ejecucion.directorio, resultado)
            ejecucion.normalizacion = normalizacion
            ejecucion.hallazgos = ejecucion.hallazgos + list(normalizacion.hallazgos)
            hay_advertencias = any(
                hallazgo.severidad == "warning" for hallazgo in ejecucion.hallazgos
            )
            if not normalizacion.publicable:
                ejecucion.estado = "no_publicado"
            elif hay_advertencias:
                ejecucion.estado = "normalizado_con_advertencias"
            else:
                ejecucion.estado = "normalizado"
        except Exception as exc:
            ejecucion.estado = "error"
            ejecucion.hallazgos.append(
                Hallazgo(
                    codigo="ERROR_INTERNO_LIMPIEZA",
                    severidad="error",
                    mensaje="La limpieza o normalización terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            )
        finally:
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)

    def _validar_silabos(
        self,
        ejecucion: Ejecucion,
        ruta_entrada: Path,
        carrera: str,
        periodo: str,
    ) -> None:
        """Valida y limpia un paquete curricular sin ejecutar aún la extracción CHH."""

        try:
            resultado = validar_silabos(ruta_entrada, carrera, periodo, ejecucion.archivo)
        except Exception as exc:
            ejecucion.estado = "error"
            ejecucion.hallazgos = [
                Hallazgo(
                    codigo="ERROR_INTERNO_VALIDACION_SILABOS",
                    severidad="error",
                    mensaje="La validación curricular terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            ]
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            return

        ejecucion.validacion_silabos = resultado
        ejecucion.hallazgos = list(resultado.hallazgos)
        if not resultado.valida:
            ejecucion.estado = "rechazado"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            return

        try:
            catalogo_global = cargar_catalogo()
            catalogo_carrera = cargar_catalogo_carrera(
                resultado.carrera,
                resultado.periodo,
            )
            ejecucion.catalogo_chh = (catalogo_carrera or catalogo_global).resumen()
            ejecucion.catalogo_chh["alcance_curricular"] = (
                "carrera" if catalogo_carrera is not None else "perfil_del_silabo"
            )
            ejecucion.catalogo_chh["carrera"] = resultado.carrera
            ejecucion.catalogo_chh["periodo"] = resultado.periodo
        except Exception as exc:
            ejecucion.catalogo_chh = {
                "disponible": False,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            }
        try:
            ejecucion.estado = "limpiando"
            ejecucion.actualizada_en = _ahora()
            usar_llm = booleano("NORMALIZADOR_CURRICULAR_LLM", True)
            if usar_llm:
                ejecucion.progreso_llm = ProgresoLimpiezaLLM(
                    fase="preparando",
                    chunks_completados=0,
                    chunks_totales=0,
                    logros_procesados=0,
                    logros_totales=0,
                    silabos_procesados=0,
                    silabos_totales=len(resultado.archivos),
                    decisiones_cacheadas=0,
                    reintentos=0,
                    silabos_detectados=0,
                    mensaje="Preparando la extracción de sílabos antes de iniciar el análisis LLM.",
                ).con_evento(
                    "Preparando la extracción de sílabos antes de iniciar el análisis LLM."
                )
            self._persistir(ejecucion)

            def actualizar_progreso_llm(progreso: ProgresoLimpiezaLLM) -> None:
                ejecucion.progreso_llm = progreso
                ejecucion.actualizada_en = _ahora()
                self._persistir(ejecucion)

            tags_traza, metadata_traza = contexto_ejecucion(
                ejecucion.id_ejecucion,
                resultado.carrera,
                resultado.periodo,
            )
            limpieza = ejecutar_flujo(
                lambda: limpiar_silabos(
                    ruta_entrada,
                    ejecucion.directorio,
                    resultado,
                    usar_llm=usar_llm,
                    inspeccionar_llm=booleano("NORMALIZADOR_CURRICULAR_INSPECTOR", True),
                    al_actualizar_progreso_llm=actualizar_progreso_llm if usar_llm else None,
                    progreso_inicial=ejecucion.progreso_llm if usar_llm else None,
                    id_ejecucion=ejecucion.id_ejecucion,
                ),
                run_name="normalizador.curricular",
                inputs={
                    "execution_id": ejecucion.id_ejecucion,
                    "career": resultado.carrera,
                    "period": resultado.periodo,
                    "files_count": len(resultado.archivos),
                },
                tags=tags_traza,
                metadata={**metadata_traza, "flow": "curricular"},
            )
            ejecucion.limpieza_silabos = limpieza
            ejecucion.hallazgos = ejecucion.hallazgos + list(limpieza.hallazgos)
            if not limpieza.publicable or any(
                hallazgo.severidad == "error" for hallazgo in ejecucion.hallazgos
            ):
                ejecucion.estado = "no_publicado"
            elif any(hallazgo.severidad == "warning" for hallazgo in ejecucion.hallazgos):
                ejecucion.estado = "limpiado_con_advertencias"
            else:
                ejecucion.estado = "limpiado"
        except Exception as exc:
            ejecucion.estado = "error"
            if ejecucion.progreso_llm is not None:
                ejecucion.progreso_llm = replace(
                    ejecucion.progreso_llm,
                    fase="error",
                    reporte_final="error",
                ).con_evento(
                    "La ejecución terminó con error; se conservan los avances registrados."
                )
            ejecucion.hallazgos.append(
                Hallazgo(
                    codigo="ERROR_INTERNO_LIMPIEZA_SILABOS",
                    severidad="error",
                    mensaje="La limpieza curricular terminó con un error interno.",
                    detalle=f"{type(exc).__name__}: {str(exc)[:200]}",
                )
            )
        finally:
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)

    def _persistir(self, ejecucion: Ejecucion) -> None:
        """Escribe el manifest para conservar evidencia aunque el proceso reinicie."""

        manifest = ejecucion.directorio / "manifest.json"
        temporal = manifest.with_suffix(".json.tmp")
        temporal.write_text(
            json.dumps(ejecucion.a_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporal.replace(manifest)


gestor_ejecuciones = GestorEjecuciones()
