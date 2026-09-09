"""Ejecuciones en segundo plano para la puerta de entrada del normalizador."""

from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from uuid import uuid4

from agente.config.settings import (
    BASE_DIR,
    booleano,
    configuracion_normalizador_curricular,
    entero,
    texto,
)
from agente.normalizador.ejecuciones_curriculares import EjecutorCurricular
from agente.normalizador.empleabilidad.catalogo import (
    cargar_catalogo,
    cargar_catalogo_carrera,
)
from agente.normalizador.empleabilidad.entrada import validar_archivo
from agente.normalizador.empleabilidad.limpieza import limpiar_archivo
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.excepciones import CancelacionSolicitada
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
from agente.normalizador.persistencia_ejecuciones import RepositorioEjecucionesPersistidas
from agente.normalizador.silabos.entrada import validar_archivo as validar_silabos
from agente.normalizador.silabos.fuente_cactus import (
    CactusExtractor,
    CactusExtractorError,
    empaquetar_archivos_cactus,
)
from agente.normalizador.silabos.limpieza import limpiar_archivo as limpiar_silabos
from agente.normalizador.silabos.salida import (
    _ARCHIVOS_CURRICULARES_FINALES,  # noqa: F401
)
from agente.observabilidad.langsmith import contexto_ejecucion, ejecutar_flujo


def _ahora() -> str:
    """Genera timestamps UTC comparables entre procesos y ejecuciones."""

    return datetime.now(UTC).isoformat()


_ESTADOS_CANCELABLES: frozenset[str] = frozenset(
    {"recibido", "extrayendo", "validando", "limpiando", "normalizando"}
)


def _resumen_aprobacion(directorio: Path) -> dict[str, object] | None:
    try:
        from agente.normalizador.silabos.aprobaciones import resumen_aprobacion_curricular

        return resumen_aprobacion_curricular(directorio)
    except (OSError, ValueError, TypeError):
        return None


class EjecucionNoCancelable(RuntimeError):
    """Indica que una ejecución no puede cambiar de estado a cancelado."""


class HistorialNoEliminable(RuntimeError):
    """Indica que una ejecución activa no puede eliminarse del historial."""


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
        self.configuracion_curricular: dict[str, object] | None = None
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
        self.fuente: dict[str, object] | None = None
        self.progreso_fuente: dict[str, object] | None = None
        self.outputs_fuente: list[dict[str, object]] = []
        self.cancelada = Event()
        self.cancelacion_solicitada = False
        self.cancelada_en: str | None = None

    def a_dict(self) -> dict[str, object]:
        return RepositorioEjecucionesPersistidas.serializar_ejecucion(self, _resumen_aprobacion)


class GestorEjecuciones:
    """Coordina validaciones cortas y persiste un manifest por ejecución."""

    def __init__(self, base_dir: Path | None = None) -> None:
        configurado = texto("NORMALIZADOR_DATA_DIR")
        self.base_dir = base_dir or Path(configurado or BASE_DIR / ".normalizador")
        self._ejecuciones: dict[str, Ejecucion] = {}
        self._bloqueo = Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="normalizador")
        self.max_historial = max(1, entero("NORMALIZADOR_HISTORIAL_MAX_EJECUCIONES", 20))
        self.retencion_dias = max(1, entero("NORMALIZADOR_HISTORIAL_RETENCION_DIAS", 15))
        self._persistencia = RepositorioEjecucionesPersistidas(
            self.base_dir,
            self.max_historial,
            self.retencion_dias,
            self._obtener_objeto,
        )

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

    def iniciar_extraccion_silabos(
        self,
        id_ejecucion: str,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
    ) -> None:
        """Programa Cactus y el pipeline curricular en una sola ejecución."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "extrayendo"
        ejecucion.fuente = {
            "tipo": "cactus",
            "estado": "extrayendo",
            "carrera": carrera,
            "periodo": periodo,
        }
        ejecucion.progreso_fuente = {
            "fase": "preparando",
            "mensaje": "Preparando la extracción desde Cactus.",
            "cursos_encontrados": 0,
            "cursos_procesados": 0,
            "archivos_descargados": 0,
            "errores": 0,
        }
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._executor.submit(
            self._extraer_y_validar_silabos,
            ejecucion,
            carrera,
            periodo,
            usuario,
            contrasena,
        )

    def marcar_rechazo(self, id_ejecucion: str, hallazgo: Hallazgo) -> None:
        """Marca un rechazo inmediato, por ejemplo por límite de carga."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        ejecucion.estado = "rechazado"
        ejecucion.hallazgos = [hallazgo]
        self._finalizar(ejecucion)

    def cancelar(self, id_ejecucion: str) -> dict[str, object]:
        """Solicita una cancelación cooperativa y la persiste inmediatamente."""

        ejecucion = self._obtener_objeto(id_ejecucion)
        if ejecucion.estado == "cancelado":
            return ejecucion.a_dict()
        if ejecucion.estado not in _ESTADOS_CANCELABLES:
            raise EjecucionNoCancelable(
                f"La ejecución está en estado {ejecucion.estado} y ya no admite cancelación."
            )
        ejecucion.cancelada.set()
        ejecucion.cancelacion_solicitada = True
        ejecucion.cancelada_en = ejecucion.cancelada_en or _ahora()
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        respuesta = ejecucion.a_dict()
        respuesta["mensaje"] = (
            "Cancelación solicitada. El lote que ya está en curso puede terminar; "
            "no se enviará otro lote al LLM."
        )
        return respuesta

    def listar_historial(self, limite: int = 20) -> dict[str, object]:
        """Lista ejecuciones recientes y aplica la política TTL/LRU."""

        return self._persistencia.listar_historial(limite)

    def obtener_reporte(self, id_ejecucion: str) -> dict[str, object]:
        """Construye un reporte JSON consolidado desde los artefactos auditables."""

        return self._persistencia.obtener_reporte(id_ejecucion)

    def eliminar_historial(self, id_ejecucion: str) -> dict[str, object]:
        """Elimina una ejecución terminal, nunca una ejecución activa."""

        try:
            ejecucion = self._obtener_objeto(id_ejecucion)
        except KeyError:
            ejecucion = None
        if ejecucion is not None and not self._persistencia.es_terminal(ejecucion.estado):
            raise HistorialNoEliminable(
                "No se puede eliminar una ejecución mientras sigue en curso."
            )
        eliminado = self._persistencia.eliminar_historial(id_ejecucion)
        with self._bloqueo:
            self._ejecuciones.pop(id_ejecucion, None)
        return eliminado

    def obtener(self, id_ejecucion: str) -> dict[str, object]:
        """Obtiene el estado serializable de una ejecución activa."""

        return self._persistencia.obtener(id_ejecucion)

    def _obtener_objeto(self, id_ejecucion: str) -> Ejecucion:
        with self._bloqueo:
            ejecucion = self._ejecuciones.get(id_ejecucion)
        if ejecucion is None:
            raise KeyError(id_ejecucion)
        return ejecucion

    def _verificar_cancelacion(self, ejecucion: Ejecucion) -> None:
        if ejecucion.cancelada.is_set():
            raise CancelacionSolicitada()

    def _cancelar_si_solicitada(self, ejecucion: Ejecucion) -> bool:
        if not ejecucion.cancelada.is_set():
            return False
        self._marcar_cancelado(ejecucion)
        return True

    def _marcar_cancelado(self, ejecucion: Ejecucion) -> None:
        ejecucion.cancelacion_solicitada = True
        ejecucion.cancelada_en = ejecucion.cancelada_en or _ahora()
        ejecucion.estado = "cancelado"
        if not any(
            hallazgo.codigo == "PROCESAMIENTO_CANCELADO" for hallazgo in ejecucion.hallazgos
        ):
            ejecucion.hallazgos.append(
                Hallazgo(
                    codigo="PROCESAMIENTO_CANCELADO",
                    severidad="warning",
                    mensaje="El procesamiento fue cancelado por el usuario.",
                    detalle="No se enviarán nuevos lotes al LLM; el lote en curso pudo terminar.",
                )
            )
        if ejecucion.progreso_llm is not None:
            ejecucion.progreso_llm = replace(
                ejecucion.progreso_llm,
                fase="cancelado",
                reporte_final="cancelado",
            ).con_evento("Procesamiento cancelado; se conservaron los artefactos de auditoría.")
        self._asegurar_reportes_cancelacion(ejecucion)
        ejecucion.actualizada_en = _ahora()

    @staticmethod
    def _asegurar_reportes_cancelacion(ejecucion: Ejecucion) -> None:
        """Crea artefactos mínimos aunque la cancelación ocurra durante extracción."""

        reportes = ejecucion.directorio / "salidas" / "reportes"
        try:
            reportes.mkdir(parents=True, exist_ok=True)
            decisiones = reportes / "decisiones_llm.jsonl"
            if not decisiones.exists():
                decisiones.write_text(
                    json.dumps(
                        {
                            "tipo": "sistema",
                            "estado": "CANCELADO",
                            "detalle": (
                                "La ejecución se canceló antes de completar el análisis LLM."
                            ),
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            analisis = reportes / "analisis_llm.json"
            if not analisis.exists():
                analisis.write_text(
                    json.dumps(
                        {
                            "estado": "CANCELADO",
                            "propuestas_pendientes": 0,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            cuarentena = reportes / "cuarentena.jsonl"
            if not cuarentena.exists():
                cuarentena.write_text("", encoding="utf-8")
        except OSError:
            # El estado cancelado debe persistir aunque el disco no permita el detalle.
            return

    def _finalizar(self, ejecucion: Ejecucion) -> None:
        """Cierra el manifest, purga temporales y aplica la retención."""

        if self._persistencia.es_terminal(ejecucion.estado):
            self._purgar_temporales(ejecucion)
        ejecucion.actualizada_en = _ahora()
        self._persistir(ejecucion)
        self._persistencia.aplicar_retencion()

    def _purgar_temporales(self, ejecucion: Ejecucion) -> None:
        """Elimina staging y capturas temporales, conservando la fuente curricular."""

        raiz = ejecucion.directorio.resolve()
        temporales = ["fuentes_curriculares", "limpios", "cactus_chrome_profile"]
        if ejecucion.tipo != "silabos":
            temporales.append("entrada")
        for relativo in temporales:
            ruta = (raiz / relativo).resolve()
            if raiz not in ruta.parents or not ruta.is_dir():
                continue
            try:
                shutil.rmtree(ruta)
            except OSError:
                # La ejecución ya terminó; una falla de limpieza no invalida los CSV.
                continue

    def _validar(self, ejecucion: Ejecucion, ruta_entrada: Path) -> None:
        """Ejecuta el gate y genera staging solo cuando la fuente es estructuralmente válida."""

        try:
            self._verificar_cancelacion(ejecucion)
            resultado = validar_archivo(ruta_entrada, ejecucion.archivo)
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
            self._finalizar(ejecucion)
            return
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
            self._finalizar(ejecucion)
            return

        ejecucion.validacion = resultado
        ejecucion.hallazgos = list(resultado.hallazgos)
        if self._cancelar_si_solicitada(ejecucion):
            self._finalizar(ejecucion)
            return
        if not resultado.valida:
            ejecucion.estado = "rechazado"
            self._finalizar(ejecucion)
            return

        try:
            ejecucion.catalogo_chh = cargar_catalogo().resumen()
        except Exception as exc:
            ejecucion.catalogo_chh = {
                "disponible": False,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            }

        try:
            self._verificar_cancelacion(ejecucion)
            ejecucion.estado = "limpiando"
            ejecucion.actualizada_en = _ahora()
            self._persistir(ejecucion)
            limpieza = limpiar_archivo(ruta_entrada, ejecucion.directorio, resultado)
            self._verificar_cancelacion(ejecucion)
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
            self._verificar_cancelacion(ejecucion)
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
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
        except Exception as exc:
            if ejecucion.cancelada.is_set():
                self._marcar_cancelado(ejecucion)
                return
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
            self._finalizar(ejecucion)

    def _validar_silabos(
        self,
        ejecucion: Ejecucion,
        ruta_entrada: Path,
        carrera: str,
        periodo: str,
    ) -> None:
        """Conserva el wrapper curricular usado por executor, API y pruebas."""

        self._ejecutor_curricular().validar_silabos(
            ejecucion,
            ruta_entrada,
            carrera,
            periodo,
            validar_entrada=validar_silabos,
            cargar_catalogo=cargar_catalogo,
            cargar_catalogo_carrera=cargar_catalogo_carrera,
            configuracion_curricular=configuracion_normalizador_curricular,
            contexto_ejecucion=contexto_ejecucion,
            ejecutar_flujo=ejecutar_flujo,
            limpiar_silabos=limpiar_silabos,
            aplicar_gate=self._aplicar_gate_de_extraccion,
        )

    def _extraer_y_validar_silabos(
        self,
        ejecucion: Ejecucion,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
    ) -> None:
        """Conserva el wrapper Cactus usado por executor, API y pruebas."""

        self._ejecutor_curricular().extraer_y_validar_silabos(
            ejecucion,
            carrera,
            periodo,
            usuario,
            contrasena,
            cactus_extractor=CactusExtractor,
            cactus_extractor_error=CactusExtractorError,
            booleano=booleano,
            entero=entero,
            empaquetar_archivos=empaquetar_archivos_cactus,
            validar_silabos=self._validar_silabos,
            registrar_error=self._registrar_error_fuente,
        )

    def _registrar_error_fuente(
        self,
        ejecucion: Ejecucion,
        codigo: str,
        detalle: str,
    ) -> None:
        self._ejecutor_curricular().registrar_error_fuente(ejecucion, codigo, detalle)

    def _aplicar_gate_de_extraccion(
        self,
        ejecucion: Ejecucion,
        limpieza: ResultadoLimpiezaSilabos,
    ) -> ResultadoLimpiezaSilabos:
        return EjecutorCurricular.aplicar_gate_de_extraccion(ejecucion, limpieza)

    def _ejecutor_curricular(self) -> EjecutorCurricular:
        """Construye el runner con las costuras resueltas en esta invocación."""

        return EjecutorCurricular(
            ahora=_ahora,
            persistir=self._persistir,
            verificar_cancelacion=self._verificar_cancelacion,
            cancelar_si_solicitada=self._cancelar_si_solicitada,
            marcar_cancelado=self._marcar_cancelado,
            finalizar=self._finalizar,
            actualizar_outputs=self._persistencia.actualizar_metadatos_outputs,
        )

    def _persistir(self, ejecucion: Ejecucion) -> None:
        """Escribe el manifest para conservar evidencia aunque el proceso reinicie."""

        self._persistencia.persistir(ejecucion)


gestor_ejecuciones = GestorEjecuciones()
