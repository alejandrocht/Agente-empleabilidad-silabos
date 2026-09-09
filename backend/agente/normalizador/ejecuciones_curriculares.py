"""Runner síncrono del flujo curricular de las ejecuciones del normalizador."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import Hallazgo, ProgresoLimpiezaLLM, ResultadoLimpiezaSilabos


class EjecutorCurricular:
    """Ejecuta el flujo curricular usando callbacks del gestor que lo coordina."""

    def __init__(
        self,
        *,
        ahora: Callable[[], str],
        persistir: Callable[[Any], None],
        verificar_cancelacion: Callable[[Any], None],
        cancelar_si_solicitada: Callable[[Any], bool],
        marcar_cancelado: Callable[[Any], None],
        finalizar: Callable[[Any], None],
        actualizar_outputs: Callable[[Path, list[dict[str, object]]], list[dict[str, object]]],
    ) -> None:
        self._ahora = ahora
        self._persistir = persistir
        self._verificar_cancelacion = verificar_cancelacion
        self._cancelar_si_solicitada = cancelar_si_solicitada
        self._marcar_cancelado = marcar_cancelado
        self._finalizar = finalizar
        self._actualizar_outputs = actualizar_outputs

    def validar_silabos(
        self,
        ejecucion: Any,
        ruta_entrada: Path,
        carrera: str,
        periodo: str,
        *,
        validar_entrada: Callable[..., Any],
        cargar_catalogo: Callable[[], Any],
        cargar_catalogo_carrera: Callable[[str, str], Any],
        configuracion_curricular: Callable[[], Any],
        contexto_ejecucion: Callable[[str, str, str], tuple[list[str], dict[str, object]]],
        ejecutar_flujo: Callable[..., Any],
        limpiar_silabos: Callable[..., ResultadoLimpiezaSilabos],
        aplicar_gate: Callable[[Any, ResultadoLimpiezaSilabos], ResultadoLimpiezaSilabos],
    ) -> None:
        """Valida, limpia y finaliza un paquete curricular de forma síncrona."""

        try:
            self._verificar_cancelacion(ejecucion)
            resultado = validar_entrada(ruta_entrada, carrera, periodo, ejecucion.archivo)
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
            self._finalizar(ejecucion)
            return
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
            ejecucion.actualizada_en = self._ahora()
            self._finalizar(ejecucion)
            return

        ejecucion.validacion_silabos = resultado
        ejecucion.hallazgos = list(resultado.hallazgos)
        if self._cancelar_si_solicitada(ejecucion):
            self._finalizar(ejecucion)
            return
        if not resultado.valida:
            ejecucion.estado = "rechazado"
            self._finalizar(ejecucion)
            return

        try:
            catalogo_global = cargar_catalogo()
            catalogo_carrera = cargar_catalogo_carrera(resultado.carrera, resultado.periodo)
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
            self._verificar_cancelacion(ejecucion)
            ejecucion.estado = "limpiando"
            ejecucion.actualizada_en = self._ahora()
            configuracion = configuracion_curricular()
            ejecucion.configuracion_curricular = configuracion.a_dict()
            usar_llm = configuracion.usar_llm
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
                ejecucion.actualizada_en = self._ahora()
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
                    al_actualizar_progreso_llm=actualizar_progreso_llm if usar_llm else None,
                    progreso_inicial=ejecucion.progreso_llm if usar_llm else None,
                    id_ejecucion=ejecucion.id_ejecucion,
                    cancelada=ejecucion.cancelada.is_set,
                    configuracion_curricular=configuracion,
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
            limpieza = aplicar_gate(ejecucion, limpieza)
            self._verificar_cancelacion(ejecucion)
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
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
        except Exception as exc:
            if ejecucion.cancelada.is_set():
                self._marcar_cancelado(ejecucion)
                return
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
            self._finalizar(ejecucion)

    def extraer_y_validar_silabos(
        self,
        ejecucion: Any,
        carrera: str,
        periodo: str,
        usuario: str,
        contrasena: str,
        *,
        cactus_extractor: Callable[..., Any],
        cactus_extractor_error: type[Exception],
        booleano: Callable[[str, bool], bool],
        entero: Callable[[str, int], int],
        empaquetar_archivos: Callable[[Path, Path], None],
        validar_silabos: Callable[[Any, Path, str, str], None],
        registrar_error: Callable[[Any, str, str], None],
    ) -> None:
        """Descarga desde Cactus y entrega un ZIP interno al flujo curricular."""

        try:
            self._verificar_cancelacion(ejecucion)
            directorio_descarga = ejecucion.directorio / "fuentes_curriculares" / "cactus"
            extractor = cactus_extractor(
                headless=booleano("NORMALIZADOR_CACTUS_HEADLESS", False),
                download_workers=entero("NORMALIZADOR_CACTUS_DOWNLOAD_WORKERS", 3),
            )

            def actualizar_progreso(progreso: dict[str, object]) -> None:
                ejecucion.progreso_fuente = dict(progreso)
                ejecucion.actualizada_en = self._ahora()
                self._persistir(ejecucion)

            resultado = extractor.extraer(
                carrera=carrera,
                periodo=periodo,
                usuario=usuario,
                contrasena=contrasena,
                directorio_salida=directorio_descarga,
                directorio_perfil=ejecucion.directorio / "cactus_chrome_profile",
                al_actualizar_progreso=actualizar_progreso,
                cancelada=ejecucion.cancelada.is_set,
            )
            usuario = ""
            contrasena = ""
            reporte = resultado.a_dict(directorio_descarga)
            ejecucion.fuente = reporte
            reporte_path = ejecucion.directorio / "salidas" / "reportes" / "extraccion_cactus.json"
            reporte_path.parent.mkdir(parents=True, exist_ok=True)
            reporte_path.write_text(
                json.dumps(reporte, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            ejecucion.outputs_fuente = self._actualizar_outputs(
                ejecucion.directorio,
                [
                    {
                        "tipo": "fuente_cactus",
                        "archivo": "salidas/reportes/extraccion_cactus.json",
                        "registros": 1,
                    }
                ],
            )
            ejecucion.actualizada_en = self._ahora()
            self._persistir(ejecucion)

            if not resultado.archivos_procesables:
                ejecucion.estado = "rechazado"
                ejecucion.hallazgos.append(
                    Hallazgo(
                        codigo="CACTUS_SIN_SILABOS_PROCESABLES",
                        severidad="error",
                        mensaje="Cactus no produjo sílabos PDF o DOCX procesables.",
                        detalle=(
                            f"cursos={resultado.cursos_encontrados}; "
                            f"descargados={resultado.archivos_descargados}"
                        ),
                    )
                )
                self._finalizar(ejecucion)
                return

            ruta_entrada = ejecucion.directorio / "entrada" / ejecucion.archivo
            empaquetar_archivos(directorio_descarga, ruta_entrada)
            ejecucion.estado = "validando"
            ejecucion.actualizada_en = self._ahora()
            self._persistir(ejecucion)
            validar_silabos(ejecucion, ruta_entrada, carrera, periodo)
        except CancelacionSolicitada:
            self._marcar_cancelado(ejecucion)
            self._finalizar(ejecucion)
        except cactus_extractor_error as exc:
            registrar_error(ejecucion, exc.codigo, exc.mensaje)
        except Exception as exc:
            registrar_error(
                ejecucion,
                "ERROR_INTERNO_EXTRACCION_CACTUS",
                f"{type(exc).__name__}: {str(exc)[:200]}",
            )
        finally:
            usuario = ""
            contrasena = ""

    def registrar_error_fuente(self, ejecucion: Any, codigo: str, detalle: str) -> None:
        """Registra un fallo de Cactus y deja la ejecución en estado terminal."""

        if ejecucion.fuente is None:
            ejecucion.fuente = {"tipo": "cactus"}
        ejecucion.fuente = {
            **ejecucion.fuente,
            "estado": "error",
            "codigo": codigo,
            "detalle": detalle,
        }
        reportes = ejecucion.directorio / "salidas" / "reportes"
        reportes.mkdir(parents=True, exist_ok=True)
        reporte = reportes / "extraccion_cactus.json"
        reporte.write_text(
            json.dumps(ejecucion.fuente, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        ejecucion.outputs_fuente = self._actualizar_outputs(
            ejecucion.directorio,
            [
                {
                    "tipo": "fuente_cactus",
                    "archivo": "salidas/reportes/extraccion_cactus.json",
                    "registros": 1,
                }
            ],
        )
        ejecucion.estado = "error"
        ejecucion.hallazgos.append(
            Hallazgo(
                codigo=codigo,
                severidad="error",
                mensaje="La extracción desde Cactus no pudo completarse.",
                detalle=detalle,
            )
        )
        self._finalizar(ejecucion)

    @staticmethod
    def aplicar_gate_de_extraccion(
        ejecucion: Any,
        limpieza: ResultadoLimpiezaSilabos,
    ) -> ResultadoLimpiezaSilabos:
        """Bloquea la publicación cuando Cactus entregó una fuente incompleta."""

        fuente = ejecucion.fuente
        if not isinstance(fuente, dict) or fuente.get("completa") is not False:
            return limpieza

        gate = dict(limpieza.release_gate)
        blockers_value = gate.get("blockers")
        blockers_items: list[object] = blockers_value if isinstance(blockers_value, list) else []
        blockers = {str(item) for item in blockers_items if item}
        blockers.add("EXTRACTION_COVERAGE_INCOMPLETE")
        checks_value = gate.get("checks")
        checks = dict(checks_value) if isinstance(checks_value, dict) else {}
        checks["source_extraction"] = {
            "ok": False,
            "cursos_encontrados": fuente.get("cursos_encontrados", 0),
            "archivos_descargados": fuente.get("archivos_descargados", 0),
            "archivos_procesables": fuente.get("archivos_procesables", 0),
            "sin_silabo": fuente.get("sin_silabo", 0),
            "fetch_fallidos": fuente.get("fetch_fallidos", 0),
            "sesiones_fallidas": fuente.get("sesiones_fallidas", 0),
            "archivos_no_soportados": fuente.get("archivos_no_soportados", 0),
        }
        gate["checks"] = checks
        gate["blockers"] = sorted(blockers)
        gate["decision"] = "BLOCK_IMPORT"
        reporte = ejecucion.directorio / "salidas" / "reportes" / "release_gate.json"
        reporte.parent.mkdir(parents=True, exist_ok=True)
        reporte.write_text(
            json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        hallazgo = Hallazgo(
            codigo="EXTRACCION_CACTUS_INCOMPLETA",
            severidad="warning",
            mensaje="La extracción desde Cactus fue parcial; la publicación quedó bloqueada.",
            detalle=(
                f"{fuente.get('archivos_procesables', 0)}/"
                f"{fuente.get('cursos_encontrados', 0)} sílabos procesables."
            ),
        )
        return replace(
            limpieza,
            publicable=False,
            release_gate=gate,
            hallazgos=(*limpieza.hallazgos, hallazgo),
        )
