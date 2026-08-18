"""Analista semántico curricular con salida estructurada y juez local.

Python conserva la extracción y la autoridad de la evidencia. El LLM interpreta
el logro dentro del perfil de carrera; el juez de este módulo solo permite pasar
decisiones que puedan verificarse contra el sílabo y los candidatos detectados.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from agente.config.settings import booleano, decimal
from agente.llm.fabrica import obtener_llm
from agente.normalizador.empleabilidad.catalogo import (
    CatalogoCHH,
    clave_concepto,
)
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import (
    EstadoReporteFinalLLM,
    FaseProgresoLLM,
    ProgresoLimpiezaLLM,
    UltimoChunkLimpiezaLLM,
)
from agente.normalizador.silabos.contexto_curricular import (
    construir_contexto_por_logro,
    construir_perfil_para_prompt,
)
from agente.normalizador.silabos.perfil_carrera import cargar_perfil_carrera
from agente.observabilidad.langsmith import invocar_llm


class ConceptoPropuesto(BaseModel):
    """Concepto sin ID: los IDs siempre los genera Python."""

    nombre: str = Field(min_length=2, max_length=180)
    descripcion: str = Field(default="", max_length=600)
    tipo: str = Field(default="", max_length=40)


class HerramientaPropuesta(BaseModel):
    """Herramienta elegida por el LLM desde evidencia curricular."""

    nombre: str = Field(min_length=2, max_length=160)
    evidencia: str = Field(default="", max_length=500)


class DecisionCurricular(BaseModel):
    """Decisión semántica para un logro específico."""

    id_habilidad_fuente: str = Field(min_length=4, max_length=100)
    competencia: ConceptoPropuesto
    habilidad: ConceptoPropuesto
    herramientas: list[HerramientaPropuesta] = Field(default_factory=list, max_length=8)
    evidencia: list[str] = Field(default_factory=list, max_length=6)
    justificacion: str = Field(default="", max_length=1200)
    confianza: float = Field(ge=0, le=1)
    requiere_revision: bool = False


class LoteDecisionesCurriculares(BaseModel):
    """Respuesta estructurada del analista para un lote de logros."""

    decisiones: list[DecisionCurricular] = Field(default_factory=list, max_length=20)


class InspeccionCurricular(BaseModel):
    """Veredicto del inspector sobre una decisión del analista."""

    id_habilidad_fuente: str = Field(min_length=4, max_length=100)
    estado: Literal["APROBAR", "REVISAR", "RECHAZAR"]
    confianza: float = Field(ge=0, le=1)
    problemas: list[str] = Field(default_factory=list, max_length=8)


class LoteInspeccionesCurriculares(BaseModel):
    inspecciones: list[InspeccionCurricular] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True, slots=True)
class ResultadoAnalisisCurricular:
    """Decisiones aprobadas y evidencia de cada llamada del analista."""

    decisiones: dict[str, DecisionCurricular]
    reportes: tuple[dict[str, object], ...]
    modelo_analista: str
    modelo_inspector: str
    lotes: int
    modelo_analista_residual: str = "no_ejecutado"
    modelo_inspector_residual: str = "no_ejecutado"
    decisiones_escaladas: int = 0
    auditoria_contexto: dict[str, object] | None = None
    progreso: ProgresoLimpiezaLLM | None = None


_VERBOS_HABILIDAD = {
    "analizar",
    "aplicar",
    "argumentar",
    "calcular",
    "comunicar",
    "construir",
    "crear",
    "desarrollar",
    "disenar",
    "elaborar",
    "evaluar",
    "explicar",
    "gestionar",
    "identificar",
    "interpretar",
    "investigar",
    "planificar",
    "proponer",
    "segmentar",
    "seleccionar",
    "utilizar",
    "formular",
    "medir",
    "administrar",
    "coordinar",
    "diagnosticar",
    "ejecutar",
    "generar",
    "optimizar",
    "presentar",
    "reconocer",
    "relacionar",
    "sustentar",
    "definir",
    "comparar",
    "estructurar",
    "implementar",
    "examinar",
    "detectar",
    "distinguir",
    "determinar",
    "diferenciar",
    "modelar",
    "representar",
    "fundamentar",
    "delimitar",
    "caracterizar",
    "articular",
    "procesar",
    "priorizar",
    "conceptualizar",
    "emplear",
    "contrastar",
    "preparar",
    "registrar",
    "vincular",
    "simular",
    "resolver",
    "valorar",
    "ajustar",
    "adaptar",
    "organizar",
    "monitorear",
    "auditar",
    "estimar",
    "predecir",
    "seguir",
    "tabular",
    "criticar",
    "ejemplificar",
    "defender",
    "realizar",
    "configurar",
    "integrar",
    "describir",
    "clasificar",
    "redactar",
    "categorizar",
}
_FORMAS_CONJUGADAS_HABILIDAD = {
    "calcula": "calcular",
    "interpreta": "interpretar",
    "evalua": "evaluar",
    "modela": "modelar",
    "gestiona": "gestionar",
    "clasifica": "clasificar",
    "optimiza": "optimizar",
}
_NOMINALIZACIONES_HABILIDAD = {
    "administracion": "administrar",
    "analisis": "analizar",
    "aplicacion": "aplicar",
    "argumentacion": "argumentar",
    "calculo": "calcular",
    "comunicacion": "comunicar",
    "construccion": "construir",
    "creacion": "crear",
    "desarrollo": "desarrollar",
    "diseno": "disenar",
    "elaboracion": "elaborar",
    "evaluacion": "evaluar",
    "explicacion": "explicar",
    "formulacion": "formular",
    "generacion": "generar",
    "gestion": "gestionar",
    "identificacion": "identificar",
    "interpretacion": "interpretar",
    "investigacion": "investigar",
    "medicion": "medir",
    "optimizacion": "optimizar",
    "planificacion": "planificar",
    "presentacion": "presentar",
    "reconocimiento": "reconocer",
    "segmentacion": "segmentar",
    "seleccion": "seleccionar",
    "sustentacion": "sustentar",
    "utilizacion": "utilizar",
    "fundamentacion": "fundamentar",
    "pronostico": "pronosticar",
    "resolucion": "resolver",
    "anticipacion": "anticipar",
    "descripcion": "describir",
    "preparacion": "preparar",
    "estructuracion": "estructurar",
    "deteccion": "detectar",
    "implementacion": "implementar",
    "monitoreo": "monitorear",
    "prototipado": "prototipar",
    "diagnostico": "diagnosticar",
    "clasificacion": "clasificar",
}
_NORMALIZACIONES_FRASES_HABILIDAD = {
    "estimacion y prediccion multivariante": (
        "Estimar y predecir fenómenos de marketing mediante métodos multivariantes"
    ),
    "elaboracion y seguimiento de cronogramas de proyectos": (
        "Elaborar y seguir cronogramas de proyectos"
    ),
    "procesamiento y tabulacion de datos de mercado": ("Procesar y tabular datos de mercado"),
    "diagnostico y delimitacion de problemas de investigacion de mercados": (
        "Diagnosticar y delimitar problemas de investigación de mercados"
    ),
    "ejecucion y seleccion de conceptos creativos": ("Ejecutar y seleccionar conceptos creativos"),
    "planificacion y ejecucion estrategica de negociaciones": (
        "Planificar y ejecutar negociaciones estratégicas"
    ),
    "evaluacion del aporte de promociones btl a la cadena de valor": (
        "Evaluar el aporte de promociones BTL a la cadena de valor"
    ),
}
_HABILIDADES_GENERICAS = {
    "comunicar",
    "integrar",
    "aplicar conceptos",
    "usar herramientas",
    "analizar información",
}
_HERRAMIENTAS_GENERICAS = {
    "herramientas",
    "herramientas digitales",
    "herramientas disruptivas",
    "recursos",
    "recursos de aprendizaje",
}
_ALIASES_CERRADOS_HERRAMIENTAS: dict[str, frozenset[str]] = {
    "excel": frozenset(("excel", "microsoft excel", "ms excel")),
    "microsoft excel": frozenset(("excel", "microsoft excel", "ms excel")),
    "ms excel": frozenset(("excel", "microsoft excel", "ms excel")),
    "word": frozenset(("word", "microsoft word", "ms word")),
    "microsoft word": frozenset(("word", "microsoft word", "ms word")),
    "ms word": frozenset(("word", "microsoft word", "ms word")),
    "google analytics": frozenset(("google analytics", "google analytics 4")),
    "google analytics 4": frozenset(("google analytics", "google analytics 4")),
}
_NOMBRES_CANONICOS_HERRAMIENTAS = {
    "excel": "Microsoft Excel",
    "microsoft excel": "Microsoft Excel",
    "ms excel": "Microsoft Excel",
    "word": "Microsoft Word",
    "microsoft word": "Microsoft Word",
    "ms word": "Microsoft Word",
    "google analytics": "Google Analytics",
    "google analytics 4": "Google Analytics",
}
_RECURSOS_ENSENANZA_GENERICOS = {
    "aula virtual",
    "diapositivas",
    "lecturas",
    "material didactico",
    "recursos de aprendizaje",
    "recursos educativos",
    "video tutorial",
    "videos tutoriales",
}


def analizar_registros_curriculares(
    registros: list[dict[str, object]],
    catalogo: CatalogoCHH,
    carrera: str,
    periodo: str,
    directorio_ejecucion: Path,
    *,
    inspeccionar: bool = True,
    al_actualizar_progreso: Callable[[ProgresoLimpiezaLLM], None] | None = None,
    progreso_inicial: ProgresoLimpiezaLLM | None = None,
    id_ejecucion: str = "",
    cancelada: Callable[[], bool] | None = None,
) -> ResultadoAnalisisCurricular:
    """Analiza todos los logros fuente y conserva fallos sin abortar el lote."""

    def verificar_cancelacion() -> None:
        """Evita iniciar otra llamada LLM después de una cancelación."""

        if cancelada is not None and cancelada():
            raise CancelacionSolicitada()

    verificar_cancelacion()

    perfil = _cargar_perfil(carrera, periodo)
    contexto_perfil = construir_contexto_por_logro({}, catalogo, perfil)
    perfil_prompt = construir_perfil_para_prompt(perfil)
    casos = tuple(_casos_curriculares(registros, catalogo, perfil))
    auditoria_contexto = _auditoria_contexto(casos, contexto_perfil)
    lotes = tuple(_trocear(casos, 8))
    cache_path = directorio_ejecucion / "salidas" / "reportes" / "decisiones_llm_cache.jsonl"
    cache = _leer_cache(cache_path)
    analista = obtener_llm("analista_curricular")
    modelo_analista = _nombre_modelo(analista)
    decisiones_crudas: dict[str, DecisionCurricular] = {}
    reportes: list[dict[str, object]] = []
    candidatos_residuales: dict[
        str, tuple[dict[str, object], DecisionCurricular | None, list[str]]
    ] = {}
    modelos_escalados: dict[str, list[str]] = {}
    usar_escalamiento = booleano("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES")
    modelo_analista_residual = "no_ejecutado"
    modelo_inspector_residual = "no_ejecutado"
    total_silabos = len(
        {str(caso.get("id_silabo") or "") for caso in casos if caso.get("id_silabo")}
    )
    logros_procesados: set[str] = set()
    silabos_procesados: set[str] = set()
    decisiones_cacheadas: set[str] = set()
    reintentos_lanzados: set[str] = set()
    reintentos = 0
    chunks_analista_completados = 0
    chunks_analista_totales = len(lotes)
    progreso_base = progreso_inicial or ProgresoLimpiezaLLM(
        fase="analista",
        chunks_completados=0,
        chunks_totales=chunks_analista_totales,
        logros_procesados=0,
        logros_totales=len(casos),
        silabos_procesados=0,
        silabos_totales=total_silabos,
        decisiones_cacheadas=0,
        reintentos=0,
        silabos_detectados=total_silabos,
    )
    progreso_actual = replace(
        progreso_base,
        fase="analista",
        chunks_completados=0,
        chunks_totales=chunks_analista_totales,
        logros_procesados=0,
        logros_totales=len(casos),
        logros_detectados=max(progreso_base.logros_detectados, len(casos)),
        silabos_detectados=max(progreso_base.silabos_detectados, total_silabos),
        silabos_procesados=0,
        silabos_totales=max(progreso_base.silabos_totales, total_silabos),
        mensaje="Analista LLM preparándose para procesar los logros detectados.",
    )

    def publicar_progreso(
        fase: FaseProgresoLLM,
        chunks_completados: int,
        chunks_totales: int,
        ultimo_chunk: UltimoChunkLimpiezaLLM | None = None,
        reporte_final: EstadoReporteFinalLLM = "pendiente",
        mensaje: str | None = None,
        logros_chunk: int = 0,
        silabos_chunk: int = 0,
    ) -> None:
        nonlocal progreso_actual
        if ultimo_chunk is not None:
            logros_chunk = ultimo_chunk.logros
            silabos_chunk = ultimo_chunk.silabos
        etiqueta_fase = {
            "analista": "Analista LLM",
            "analista_residual": "Analista residual",
            "inspector": "Inspector LLM",
            "inspector_residual": "Inspector residual",
        }.get(fase, fase.capitalize())
        mensaje_evento = mensaje or (
            (
                f"Chunk {chunks_completados}/{chunks_totales} de {etiqueta_fase} completado: "
                f"{logros_chunk} logros y {silabos_chunk} sílabos únicos."
            )
            if ultimo_chunk is not None
            else f"{etiqueta_fase}: {chunks_completados}/{chunks_totales} chunks completados."
        )
        progreso_actual = ProgresoLimpiezaLLM(
            fase=fase,
            chunks_completados=chunks_completados,
            chunks_totales=chunks_totales,
            logros_procesados=len(logros_procesados),
            logros_totales=len(casos),
            silabos_procesados=len(silabos_procesados),
            silabos_detectados=max(progreso_actual.silabos_detectados, total_silabos),
            silabos_totales=max(progreso_actual.silabos_totales, total_silabos),
            decisiones_cacheadas=len(decisiones_cacheadas),
            reintentos=reintentos,
            logros_detectados=max(progreso_actual.logros_detectados, len(casos)),
            eventos=progreso_actual.eventos,
            ultimo_chunk=ultimo_chunk,
            reporte_final=reporte_final,
        ).con_evento(
            mensaje_evento,
            logros_chunk=logros_chunk,
            silabos_chunk=silabos_chunk,
        )
        if al_actualizar_progreso is not None:
            al_actualizar_progreso(progreso_actual)

    publicar_progreso(
        "analista",
        0,
        chunks_analista_totales,
        mensaje="Analista LLM listo: iniciando el primer chunk.",
    )

    for indice_lote, lote in enumerate(lotes, start=1):
        verificar_cancelacion()
        clave_lote = _clave_lote(lote, perfil, modelo_analista)
        lote_respuesta = cache.get(clave_lote)
        if lote_respuesta is not None:
            decisiones_cacheadas.update(str(caso["id_habilidad_fuente"]) for caso in lote)
        if lote_respuesta is None:
            verificar_cancelacion()
            try:
                respuesta = _invocar_analista(
                    analista,
                    lote,
                    perfil_prompt,
                    carrera,
                    periodo,
                    id_ejecucion=id_ejecucion,
                    chunk=indice_lote,
                )
                lote_respuesta = respuesta.model_dump(mode="json")
                cache[clave_lote] = lote_respuesta
                _guardar_cache(cache_path, cache)
                decisiones_cacheadas.update(str(caso["id_habilidad_fuente"]) for caso in lote)
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                reportes.append(
                    {
                        "tipo": "analista",
                        "estado": "ERROR",
                        "clave_lote": clave_lote,
                        "detalle": f"{type(exc).__name__}: {str(exc)[:300]}",
                    }
                )
                logros_procesados.update(str(caso["id_habilidad_fuente"]) for caso in lote)
                silabos_procesados.update(
                    str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")
                )
                chunks_analista_completados += 1
                publicar_progreso(
                    "analista",
                    chunks_analista_completados,
                    chunks_analista_totales,
                    UltimoChunkLimpiezaLLM(
                        "analista",
                        len(lote),
                        len(
                            {
                                str(caso.get("id_silabo") or "")
                                for caso in lote
                                if caso.get("id_silabo")
                            }
                        ),
                    ),
                )
                continue
        try:
            respuesta = LoteDecisionesCurriculares.model_validate(lote_respuesta)
        except Exception as exc:
            reportes.append(
                {
                    "tipo": "analista",
                    "estado": "RESPUESTA_INVALIDA",
                    "clave_lote": clave_lote,
                    "detalle": f"{type(exc).__name__}: {str(exc)[:300]}",
                }
            )
            logros_procesados.update(str(caso["id_habilidad_fuente"]) for caso in lote)
            silabos_procesados.update(
                str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")
            )
            chunks_analista_completados += 1
            publicar_progreso(
                "analista",
                chunks_analista_completados,
                chunks_analista_totales,
                UltimoChunkLimpiezaLLM(
                    "analista",
                    len(lote),
                    len(
                        {str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")}
                    ),
                ),
            )
            continue
        por_id: dict[str, dict[str, object]] = {
            str(caso["id_habilidad_fuente"]): caso for caso in lote
        }
        ids_respondidos = {
            decision.id_habilidad_fuente
            for decision in respuesta.decisiones
            if decision.id_habilidad_fuente in por_id
        }
        respuestas = [(respuesta, set(por_id))]
        ids_omitidos = [
            id_habilidad for id_habilidad in por_id if id_habilidad not in ids_respondidos
        ]
        if ids_omitidos:
            lote_reintento = tuple(por_id[id_habilidad] for id_habilidad in ids_omitidos)
            clave_reintento = f"reintento:{_clave_lote(lote_reintento, perfil, modelo_analista)}"
            if clave_reintento not in reintentos_lanzados:
                reintentos_lanzados.add(clave_reintento)
                reintentos += 1
            respuesta_reintento = cache.get(clave_reintento)
            if respuesta_reintento is not None:
                decisiones_cacheadas.update(
                    str(caso["id_habilidad_fuente"]) for caso in lote_reintento
                )
            try:
                if respuesta_reintento is None:
                    verificar_cancelacion()
                    respuesta_modelo = _invocar_analista(
                        analista,
                        lote_reintento,
                        perfil_prompt,
                        carrera,
                        periodo,
                        id_ejecucion=id_ejecucion,
                        chunk=indice_lote,
                        reintento=True,
                    )
                    respuesta_reintento = respuesta_modelo.model_dump(mode="json")
                    cache[clave_reintento] = respuesta_reintento
                    _guardar_cache(cache_path, cache)
                    decisiones_cacheadas.update(
                        str(caso["id_habilidad_fuente"]) for caso in lote_reintento
                    )
                respuesta_modelo = LoteDecisionesCurriculares.model_validate(respuesta_reintento)
                ids_recuperados = [
                    decision.id_habilidad_fuente
                    for decision in respuesta_modelo.decisiones
                    if decision.id_habilidad_fuente in ids_omitidos
                ]
                ids_respondidos.update(ids_recuperados)
                respuestas.append((respuesta_modelo, set(ids_omitidos)))
                reportes.append(
                    _reporte_reintento_omitidos(
                        clave_lote,
                        ids_omitidos,
                        ids_recuperados,
                    )
                )
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                reportes.append(
                    _reporte_reintento_omitidos(
                        clave_lote,
                        ids_omitidos,
                        [],
                        detalle=f"{type(exc).__name__}: {str(exc)[:300]}",
                    )
                )

        for respuesta_lote, ids_permitidos in respuestas:
            for decision in respuesta_lote.decisiones:
                caso = por_id.get(decision.id_habilidad_fuente)
                if caso is None:
                    reportes.append(_reporte_decision(decision, "RECHAZADA_ID_NO_DECLARADO"))
                    continue
                if decision.id_habilidad_fuente not in ids_permitidos:
                    reportes.append(
                        _reporte_decision(
                            decision,
                            "RECHAZADA_ID_NO_SOLICITADO_EN_REINTENTO",
                        )
                    )
                    continue
                # Algunos modelos omiten el campo aunque la evidencia esté en el
                # caso. Python puede completar únicamente con el logro literal;
                # nunca fabrica una cita ni acepta un caso sin texto fuente.
                decision = _completar_evidencia(decision, caso)
                decision = _normalizar_habilidad(decision)
                errores = _validar_decision(decision, caso)
                if errores:
                    if usar_escalamiento and _errores_residuales_escalables(errores):
                        candidatos_residuales[decision.id_habilidad_fuente] = (
                            caso,
                            decision,
                            errores,
                        )
                        continue
                    reportes.append(_reporte_decision(decision, "REVISAR_VALIDACION", errores))
                    continue
                decisiones_crudas[decision.id_habilidad_fuente] = decision
        for id_habilidad, caso in por_id.items():
            if id_habilidad not in ids_respondidos:
                reportes.append(_reporte_sin_decision_llm(caso))
        logros_procesados.update(por_id)
        silabos_procesados.update(
            str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")
        )
        chunks_analista_completados += 1
        publicar_progreso(
            "analista",
            chunks_analista_completados,
            chunks_analista_totales,
            UltimoChunkLimpiezaLLM(
                "analista",
                len(lote),
                len({str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")}),
            ),
        )

    if candidatos_residuales:
        analista_residual = obtener_llm("analista_curricular_residual")
        modelo_analista_residual = _nombre_modelo(analista_residual)
        lotes_residuales = tuple(
            _trocear(tuple(caso for caso, _, _ in candidatos_residuales.values()), 8)
        )
        chunks_residual_completados = 0
        publicar_progreso(
            "analista_residual",
            chunks_residual_completados,
            len(lotes_residuales),
            mensaje=(
                "Analista residual listo: revisando candidatos que requieren una segunda pasada."
            ),
        )
        for indice_lote, lote in enumerate(lotes_residuales, start=1):
            verificar_cancelacion()
            por_id = {str(caso["id_habilidad_fuente"]): caso for caso in lote}
            for id_habilidad in por_id:
                modelos_escalados.setdefault(id_habilidad, []).append(modelo_analista_residual)
            try:
                verificar_cancelacion()
                respuesta_residual = _invocar_analista(
                    analista_residual,
                    lote,
                    perfil_prompt,
                    carrera,
                    periodo,
                    id_ejecucion=id_ejecucion,
                    chunk=indice_lote,
                    rol="analista_curricular_residual",
                )
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                reportes.append(
                    {
                        "tipo": "analista_residual",
                        "estado": "ERROR",
                        "detalle": f"{type(exc).__name__}: {str(exc)[:300]}",
                    }
                )
                respuesta_residual = LoteDecisionesCurriculares()
            procesados: set[str] = set()
            for decision in respuesta_residual.decisiones:
                caso = por_id.get(decision.id_habilidad_fuente)
                if caso is None:
                    reportes.append(_reporte_decision(decision, "RECHAZADA_ID_NO_DECLARADO"))
                    continue
                procesados.add(decision.id_habilidad_fuente)
                decision = _completar_evidencia(decision, caso)
                decision = _normalizar_habilidad(decision)
                errores = _validar_decision(decision, caso)
                if errores:
                    reportes.append(
                        _reporte_decision(
                            decision,
                            "REVISAR_VALIDACION",
                            errores,
                            modelos_escalados=modelos_escalados[decision.id_habilidad_fuente],
                        )
                    )
                    continue
                decisiones_crudas[decision.id_habilidad_fuente] = decision
            for id_habilidad in por_id:
                if id_habilidad in procesados:
                    continue
                caso, _, errores = candidatos_residuales[id_habilidad]
                reportes.append(
                    _reporte_sin_decision_llm(
                        caso,
                        errores,
                        modelos_escalados[id_habilidad],
                    )
                )
            chunks_residual_completados += 1
            publicar_progreso(
                "analista_residual",
                chunks_residual_completados,
                len(lotes_residuales),
                UltimoChunkLimpiezaLLM(
                    "analista",
                    len(lote),
                    len(
                        {str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")}
                    ),
                ),
            )

    inspecciones: dict[str, InspeccionCurricular] = {}
    modelo_inspector = "no_ejecutado"
    if inspeccionar and decisiones_crudas:
        inspector = obtener_llm("inspector_curricular")
        modelo_inspector = _nombre_modelo(inspector)
        lotes_inspector = tuple(
            _trocear(
                tuple(caso for caso in casos if caso["id_habilidad_fuente"] in decisiones_crudas),
                8,
            )
        )
        chunks_inspector_completados = 0
        publicar_progreso(
            "inspector",
            0,
            len(lotes_inspector),
            mensaje="Inspector LLM listo: validando las decisiones del analista.",
        )
        for indice_lote, lote in enumerate(lotes_inspector, start=1):
            verificar_cancelacion()
            decisiones = [decisiones_crudas[str(caso["id_habilidad_fuente"])] for caso in lote]
            try:
                verificar_cancelacion()
                respuesta_inspector = _invocar_inspector(
                    inspector,
                    lote,
                    decisiones,
                    perfil_prompt,
                    carrera=carrera,
                    periodo=periodo,
                    id_ejecucion=id_ejecucion,
                    chunk=indice_lote,
                )
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                reportes.append(
                    {
                        "tipo": "inspector",
                        "estado": "ERROR",
                        "detalle": f"{type(exc).__name__}: {str(exc)[:300]}",
                    }
                )
                logros_procesados.update(str(caso["id_habilidad_fuente"]) for caso in lote)
                silabos_procesados.update(
                    str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")
                )
                chunks_inspector_completados += 1
                publicar_progreso(
                    "inspector",
                    chunks_inspector_completados,
                    len(lotes_inspector),
                    UltimoChunkLimpiezaLLM(
                        "inspector",
                        len(lote),
                        len(
                            {
                                str(caso.get("id_silabo") or "")
                                for caso in lote
                                if caso.get("id_silabo")
                            }
                        ),
                    ),
                )
                continue
            for inspeccion_item in respuesta_inspector.inspecciones:
                inspecciones[inspeccion_item.id_habilidad_fuente] = inspeccion_item
            logros_procesados.update(str(caso["id_habilidad_fuente"]) for caso in lote)
            silabos_procesados.update(
                str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")
            )
            chunks_inspector_completados += 1
            publicar_progreso(
                "inspector",
                chunks_inspector_completados,
                len(lotes_inspector),
                UltimoChunkLimpiezaLLM(
                    "inspector",
                    len(lote),
                    len(
                        {str(caso.get("id_silabo") or "") for caso in lote if caso.get("id_silabo")}
                    ),
                ),
            )

    casos_para_reinspeccion = tuple(
        caso
        for caso in casos
        if (
            str(caso["id_habilidad_fuente"]) in decisiones_crudas
            and inspecciones.get(str(caso["id_habilidad_fuente"])) is not None
            and inspecciones[str(caso["id_habilidad_fuente"])].estado == "REVISAR"
        )
    )
    if usar_escalamiento and casos_para_reinspeccion:
        inspector_residual = obtener_llm("inspector_curricular_residual")
        modelo_inspector_residual = _nombre_modelo(inspector_residual)
        lotes_inspector_residual = tuple(_trocear(casos_para_reinspeccion, 8))
        chunks_inspector_residual_completados = 0
        publicar_progreso(
            "inspector_residual",
            0,
            len(lotes_inspector_residual),
            mensaje="Inspector residual listo: revisando decisiones con observaciones.",
        )
        for indice_lote, lote in enumerate(lotes_inspector_residual, start=1):
            verificar_cancelacion()
            decisiones = [decisiones_crudas[str(caso["id_habilidad_fuente"])] for caso in lote]
            ids_lote: set[str] = {decision.id_habilidad_fuente for decision in decisiones}
            for id_habilidad in ids_lote:
                modelos_escalados.setdefault(id_habilidad, []).append(modelo_inspector_residual)
            try:
                verificar_cancelacion()
                respuesta_inspeccion_residual = _invocar_inspector(
                    inspector_residual,
                    lote,
                    decisiones,
                    perfil_prompt,
                    carrera=carrera,
                    periodo=periodo,
                    id_ejecucion=id_ejecucion,
                    chunk=indice_lote,
                    rol="inspector_curricular_residual",
                    reintento=True,
                )
            except CancelacionSolicitada:
                raise
            except Exception as exc:
                reportes.append(
                    {
                        "tipo": "inspector_residual",
                        "estado": "ERROR",
                        "detalle": f"{type(exc).__name__}: {str(exc)[:300]}",
                    }
                )
            else:
                for inspeccion_item in respuesta_inspeccion_residual.inspecciones:
                    if inspeccion_item.id_habilidad_fuente in ids_lote:
                        inspecciones[inspeccion_item.id_habilidad_fuente] = inspeccion_item
            chunks_inspector_residual_completados += 1
            publicar_progreso(
                "inspector_residual",
                chunks_inspector_residual_completados,
                len(lotes_inspector_residual),
                UltimoChunkLimpiezaLLM(
                    "inspector_residual",
                    len(ids_lote),
                    len(
                        {
                            str(caso.get("id_silabo") or "")
                            for caso in lote
                            if caso.get("id_silabo")
                        }
                    ),
                ),
            )

    aprobadas: dict[str, DecisionCurricular] = {}
    for id_habilidad, decision in decisiones_crudas.items():
        inspeccion = inspecciones.get(id_habilidad)
        if inspeccionar and (
            inspeccion is None
            or inspeccion.estado != "APROBAR"
            or inspeccion.confianza < _confianza_minima()
        ):
            reportes.append(
                _reporte_decision(
                    decision,
                    "REVISAR_INSPECTOR",
                    inspeccion.problemas if inspeccion else ["Sin veredicto del inspector"],
                    inspeccion,
                    modelos_escalados=modelos_escalados.get(id_habilidad, []),
                )
            )
            continue
        aprobadas[id_habilidad] = decision
        reportes.append(
            _reporte_decision(
                decision,
                "ACEPTADA",
                inspeccion=inspeccion,
                modelos_escalados=modelos_escalados.get(id_habilidad, []),
            )
        )

    _asegurar_cobertura_reportes(casos, reportes)
    for reporte in reportes:
        reporte["contexto_auditoria"] = auditoria_contexto

    publicar_progreso(
        "finalizando",
        progreso_actual.chunks_completados,
        progreso_actual.chunks_totales,
        progreso_actual.ultimo_chunk,
    )
    return ResultadoAnalisisCurricular(
        decisiones=aprobadas,
        reportes=tuple(reportes),
        modelo_analista=modelo_analista,
        modelo_inspector=modelo_inspector,
        lotes=len(lotes),
        modelo_analista_residual=modelo_analista_residual,
        modelo_inspector_residual=modelo_inspector_residual,
        decisiones_escaladas=len(modelos_escalados),
        auditoria_contexto=auditoria_contexto,
        progreso=progreso_actual,
    )


def _invocar_analista(
    llm: object,
    lote: tuple[dict[str, object], ...],
    perfil_prompt: dict[str, object],
    carrera: str,
    periodo: str,
    *,
    rol: str = "analista_curricular",
    id_ejecucion: str = "",
    chunk: int | None = None,
    reintento: bool = False,
) -> LoteDecisionesCurriculares:
    prompt = _prompt_analista(lote, perfil_prompt, carrera, periodo)
    estructurado = llm.with_structured_output(LoteDecisionesCurriculares)  # type: ignore[attr-defined]
    respuesta = invocar_llm(
        estructurado,
        prompt,
        rol=rol,
        id_ejecucion=id_ejecucion,
        carrera=carrera,
        periodo=periodo,
        chunk=chunk,
        reintento=reintento,
    )
    return LoteDecisionesCurriculares.model_validate(respuesta)


def _invocar_inspector(
    llm: object,
    lote: tuple[dict[str, object], ...],
    decisiones: list[DecisionCurricular],
    perfil_prompt: dict[str, object],
    *,
    rol: str = "inspector_curricular",
    carrera: str = "",
    periodo: str = "",
    id_ejecucion: str = "",
    chunk: int | None = None,
    reintento: bool = False,
) -> LoteInspeccionesCurriculares:
    prompt = _prompt_inspector(lote, decisiones, perfil_prompt)
    estructurado = llm.with_structured_output(LoteInspeccionesCurriculares)  # type: ignore[attr-defined]
    respuesta = invocar_llm(
        estructurado,
        prompt,
        rol=rol,
        id_ejecucion=id_ejecucion,
        carrera=carrera,
        periodo=periodo,
        chunk=chunk,
        reintento=reintento,
    )
    return LoteInspeccionesCurriculares.model_validate(respuesta)


def _prompt_analista(
    lote: tuple[dict[str, object], ...],
    perfil_prompt: dict[str, object],
    carrera: str,
    periodo: str,
) -> str:
    return (
        "Eres el analista curricular senior de una universidad. Trabajas con el perfil "
        f"de {carrera} del periodo {periodo}. El sílabo es la única fuente de verdad.\n\n"
        "Tu tarea es representar TODOS los logros específicos, no reducirlos a los matches "
        "del catálogo. Propón una habilidad observable por logro, una competencia profesional "
        "que agrupe la habilidad y herramientas solo cuando aparezcan en la evidencia. Puedes "
        "crear conceptos nuevos si el sílabo los respalda. No inventes IDs ni evidencia. No uses "
        "la taxonomía de Ingeniería de Sistemas para interpretar Marketing.\n\n"
        "Perfil curado y defensivo:\n"
        f"{json.dumps(perfil_prompt, ensure_ascii=False, indent=2)}\n\n"
        "Devuelve una decisión por cada id_habilidad_fuente, incluso si requiere_revision=true. "
        "La habilidad debe comenzar con una acción profesional y tener verbo + objeto. La "
        "evidencia debe copiar fragmentos exactos del caso.\n\n"
        f"CASOS:\n{json.dumps(list(lote), ensure_ascii=False, indent=2)}"
    )


def _prompt_inspector(
    lote: tuple[dict[str, object], ...],
    decisiones: list[DecisionCurricular],
    perfil_prompt: dict[str, object],
) -> str:
    propuestas = [decision.model_dump(mode="json") for decision in decisiones]
    return (
        "Eres inspector adversarial de decisiones curriculares. Verifica cada propuesta contra "
        "el texto fuente y el perfil de carrera. Aprueba si la habilidad es observable y la "
        "competencia es disciplinar. La herramienta es opcional: si no existe una herramienta "
        "concreta en el sílabo, aprueba la cadena sin herramienta. Si se propone una herramienta, "
        "exige evidencia explícita y rechaza herramientas genéricas o inventadas. Rechaza el uso "
        "de competencias de Sistemas por sesgo de catálogo, las habilidades genéricas y cualquier "
        "evidencia inventada. Si hay duda, usa REVISAR.\n\n"
        f"PERFIL CURADO:\n{json.dumps(perfil_prompt, ensure_ascii=False, indent=2)}\n\n"
        f"CASOS:\n{json.dumps(list(lote), ensure_ascii=False, indent=2)}\n\n"
        f"PROPUESTAS:\n{json.dumps(propuestas, ensure_ascii=False, indent=2)}"
    )


def _casos_curriculares(
    registros: list[dict[str, object]],
    catalogo: CatalogoCHH,
    perfil: dict[str, object],
) -> Iterable[dict[str, object]]:
    for registro in registros:
        datos = registro.get("datos")
        if not isinstance(datos, dict):
            continue
        id_silabo = str(registro.get("id_silabo") or "")
        archivo = ""
        origen = registro.get("origen")
        if isinstance(origen, dict):
            archivo = str(origen.get("archivo") or "")
        declaraciones = datos.get("competencias_declaradas")
        outcomes = datos.get("logros_especificos")
        if not isinstance(outcomes, list):
            continue
        contexto = " ".join(
            str(datos.get(campo) or "")
            for campo in ("curso", "sumilla", "logro_general", "texto_relevante")
        )
        for logro in outcomes:
            if not isinstance(logro, dict):
                continue
            descripcion = str(logro.get("descripcion") or "").strip()
            etiqueta = str(logro.get("etiqueta") or "").strip().upper()
            if not descripcion:
                continue
            id_habilidad = _hash_id("HAB_SRC", id_silabo, etiqueta, descripcion)
            evidencia_herramientas = datos.get("herramientas_evidencia")
            evidencias_estructuradas = (
                list(evidencia_herramientas) if isinstance(evidencia_herramientas, list) else []
            )
            evidencias_estructuradas.extend(_evidencias_programa_analitico(datos))
            evidencias_candidatas = [
                *evidencias_estructuradas,
                {"seccion": "Logro de aprendizaje", "texto": descripcion},
            ]
            herramientas: list[str] = []
            for item in evidencias_estructuradas:
                if not isinstance(item, dict):
                    continue
                texto = str(item.get("texto") or "")
                herramientas.extend(
                    concepto.nombre for concepto in catalogo.buscar(texto).get("herramienta", ())
                )
            caso: dict[str, object] = {
                "id_habilidad_fuente": id_habilidad,
                "id_silabo": id_silabo,
                "archivo": archivo,
                "curso": str(datos.get("curso") or ""),
                "sumilla": str(datos.get("sumilla") or ""),
                "logro_general": str(datos.get("logro_general") or ""),
                "etiqueta_logro": etiqueta,
                "logro": descripcion,
                "competencias_declaradas": declaraciones if isinstance(declaraciones, list) else [],
                "contenido_relacionado": contexto[:5000],
                "herramientas_detectadas": sorted(set(herramientas)),
                "evidencia_herramientas": evidencias_estructuradas,
                "evidencia_herramientas_candidata": evidencias_candidatas,
            }
            caso["contexto_recuperado"] = construir_contexto_por_logro(caso, catalogo, perfil)
            yield caso


def _auditoria_contexto(
    casos: tuple[dict[str, object], ...],
    contexto_perfil: dict[str, object],
) -> dict[str, object]:
    perfil = cast(dict[str, str], contexto_perfil["perfil_referencia"])
    fingerprints = [
        str(contexto.get("fingerprint") or "")
        for caso in casos
        if isinstance(contexto := caso.get("contexto_recuperado"), dict)
    ]
    payload = json.dumps(fingerprints, ensure_ascii=False, separators=(",", ":"))
    return {
        "version_contexto": contexto_perfil["version_contexto"],
        "version_catalogo": cast(dict[str, object], contexto_perfil["catalogo"])["version"],
        "estado_perfil": perfil["estado"],
        "revision_perfil": perfil["revision"],
        "hash_perfil": perfil["hash"],
        "hash_contextos": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
    }


def _evidencias_programa_analitico(datos: dict[str, object]) -> list[dict[str, str]]:
    """Expone solo contenido curricular útil como evidencia estructurada de herramientas."""

    programa = datos.get("programa_analitico")
    if not isinstance(programa, list):
        return []
    evidencias: list[dict[str, str]] = []
    for item in programa:
        texto = str(item).strip()
        clave = clave_concepto(texto)
        if not texto or _programa_es_recurso_no_evidenciable(texto, clave):
            continue
        evidencias.append({"seccion": "Programa analítico", "texto": texto})
    return evidencias


def _programa_es_recurso_no_evidenciable(texto: str, clave: str) -> bool:
    texto_minusculas = texto.lower()
    return (
        "bibliografia" in clave
        or "referencia bibliografica" in clave
        or "http://" in texto_minusculas
        or "https://" in texto_minusculas
        or "www." in texto_minusculas
        or any(recurso in clave for recurso in _RECURSOS_ENSENANZA_GENERICOS)
    )


def _validar_decision(
    decision: DecisionCurricular,
    caso: dict[str, object],
) -> list[str]:
    errores: list[str] = []
    nombre_habilidad = clave_concepto(decision.habilidad.nombre)
    if nombre_habilidad in _HABILIDADES_GENERICAS:
        errores.append("HABILIDAD_GENERICA")
    tokens = nombre_habilidad.split()
    if len(tokens) < 2 or not any(token in _VERBOS_HABILIDAD for token in tokens[:2]):
        errores.append("HABILIDAD_SIN_VERBO_OBSERVABLE")
    if not clave_concepto(decision.competencia.nombre):
        errores.append("COMPETENCIA_VACIA")
    fuente = " ".join(
        str(caso.get(campo) or "")
        for campo in ("curso", "sumilla", "logro_general", "logro", "contenido_relacionado")
    )
    fuente_clave = clave_concepto(fuente)
    if not decision.evidencia:
        errores.append("SIN_EVIDENCIA_LLM")
    elif not any(_evidencia_en_texto(evidencia, fuente_clave) for evidencia in decision.evidencia):
        errores.append("EVIDENCIA_NO_ENCONTRADA")
    herramientas_detectadas = caso.get("herramientas_detectadas")
    if not isinstance(herramientas_detectadas, list):
        herramientas_detectadas = []
    disponibles = {clave_concepto(str(nombre)) for nombre in herramientas_detectadas}
    for herramienta in decision.herramientas:
        herramienta_existente = _nombre_herramienta_coincide(herramienta.nombre, disponibles)
        herramienta_nueva = _herramienta_nueva_evidenciada(
            herramienta.nombre, herramienta.evidencia, caso
        )
        if not herramienta_existente and not herramienta_nueva:
            errores.append(f"HERRAMIENTA_NO_DETECTADA:{herramienta.nombre}")
    if decision.confianza < _confianza_minima():
        errores.append("CONFIANZA_BAJA")
    if decision.requiere_revision:
        errores.append("LLM_SOLICITA_REVISION")
    return errores


def _errores_residuales_escalables(errores: list[str]) -> bool:
    """Escala solo incertidumbre semántica declarada por el modelo."""

    return bool(errores) and set(errores).issubset({"CONFIANZA_BAJA", "LLM_SOLICITA_REVISION"})


def _reporte_sin_decision_llm(
    caso: dict[str, object],
    problemas: list[str] | None = None,
    modelos_escalados: list[str] | None = None,
) -> dict[str, object]:
    """Registra un logro que el analista no representó, sin fabricar una decisión."""

    reporte: dict[str, object] = {
        "tipo": "decision_curricular",
        "estado": "REVISAR_SIN_DECISION_LLM",
        "id_habilidad_fuente": str(caso["id_habilidad_fuente"]),
        "problemas": problemas or ["SIN_DECISION_LLM"],
    }
    if modelos_escalados:
        reporte["modelos_escalados"] = modelos_escalados
    return reporte


def _reporte_reintento_omitidos(
    clave_lote: str,
    ids_habilidad_fuente: list[str],
    ids_recuperados: list[str],
    detalle: str = "",
) -> dict[str, object]:
    """Registra el único reintento permitido para IDs omitidos en un lote."""

    recuperados = list(dict.fromkeys(ids_recuperados))
    reporte: dict[str, object] = {
        "tipo": "analista_reintento",
        "estado": "COMPLETADO" if not detalle else "ERROR",
        "clave_lote": clave_lote,
        "ids_habilidad_fuente": ids_habilidad_fuente,
        "ids_recuperados": recuperados,
        "ids_sin_decision": [
            id_habilidad for id_habilidad in ids_habilidad_fuente if id_habilidad not in recuperados
        ],
    }
    if detalle:
        reporte["detalle"] = detalle
    return reporte


def _asegurar_cobertura_reportes(
    casos: tuple[dict[str, object], ...],
    reportes: list[dict[str, object]],
) -> None:
    """Evita que un caso fuente termine sin una decisión ni una traza auditable."""

    ids_reportados = {
        str(reporte["id_habilidad_fuente"])
        for reporte in reportes
        if isinstance(reporte.get("id_habilidad_fuente"), str)
        and (
            str(reporte.get("estado", "")) == "ACEPTADA"
            or str(reporte.get("estado", "")).startswith(("REVISAR", "ERROR"))
        )
    }
    for caso in casos:
        if str(caso["id_habilidad_fuente"]) not in ids_reportados:
            reportes.append(_reporte_sin_decision_llm(caso))


def _completar_evidencia(
    decision: DecisionCurricular,
    caso: dict[str, object],
) -> DecisionCurricular:
    """Completa evidencia omitida por el LLM usando el logro ya extraído."""

    if decision.evidencia:
        return decision
    logro = str(caso.get("logro") or "").strip()
    if not logro:
        return decision
    return decision.model_copy(update={"evidencia": [logro]})


def _normalizar_habilidad_nominalizada(
    decision: DecisionCurricular,
) -> DecisionCurricular:
    """Reemplaza solo la primera nominalización explícitamente admitida."""

    nombre = decision.habilidad.nombre
    primera_palabra, separador, resto = nombre.partition(" ")
    infinitivo = _NOMINALIZACIONES_HABILIDAD.get(clave_concepto(primera_palabra))
    if infinitivo is None or not separador or not resto.startswith("de "):
        return decision
    if primera_palabra[:1].isupper():
        infinitivo = infinitivo.capitalize()
    habilidad = decision.habilidad.model_copy(
        update={"nombre": f"{infinitivo} {resto.removeprefix('de ')}"}
    )
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad_forma_conjugada(
    decision: DecisionCurricular,
) -> DecisionCurricular:
    """Convierte únicamente formas conjugadas incluidas en el mapa cerrado."""

    nombre = decision.habilidad.nombre
    primera_palabra, separador, resto = nombre.partition(" ")
    infinitivo = _FORMAS_CONJUGADAS_HABILIDAD.get(clave_concepto(primera_palabra))
    if infinitivo is None or not separador:
        return decision
    if primera_palabra[:1].isupper():
        infinitivo = infinitivo.capitalize()
    habilidad = decision.habilidad.model_copy(update={"nombre": f"{infinitivo}{separador}{resto}"})
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad_frase_cerrada(
    decision: DecisionCurricular,
) -> DecisionCurricular:
    """Aplica solo las siete frases auditadas, sin ampliar el patrón."""

    nombre = decision.habilidad.nombre
    reemplazo = _NORMALIZACIONES_FRASES_HABILIDAD.get(clave_concepto(nombre))
    if reemplazo is None:
        return decision
    if nombre[:1].islower():
        reemplazo = reemplazo[:1].lower() + reemplazo[1:]
    habilidad = decision.habilidad.model_copy(update={"nombre": reemplazo})
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad(decision: DecisionCurricular) -> DecisionCurricular:
    """Normaliza solo formas verbales, nominalizaciones y frases autorizadas."""

    decision = _normalizar_habilidad_forma_conjugada(decision)
    decision = _normalizar_habilidad_nominalizada(decision)
    return _normalizar_habilidad_frase_cerrada(decision)


def _evidencia_en_texto(fragmento: str, fuente_normalizada: str) -> bool:
    evidencia = clave_concepto(fragmento)
    if len(evidencia) < 8:
        return False
    if evidencia in fuente_normalizada:
        return True
    tokens = set(evidencia.split())
    return len(tokens & set(fuente_normalizada.split())) / len(tokens) >= 0.75


def _nombre_herramienta_coincide(nombre: str, disponibles: set[str]) -> bool:
    """Acepta solo el nombre detectado o aliases gráficos inocuos."""

    clave = clave_concepto(nombre)
    return bool(_claves_herramienta_cerradas(clave) & disponibles)


def _claves_herramienta_cerradas(nombre: str) -> frozenset[str]:
    """Devuelve el nombre normalizado y solo sus aliases explícitamente aprobados."""

    clave = clave_concepto(nombre)
    if not clave:
        return frozenset()
    return _ALIASES_CERRADOS_HERRAMIENTAS.get(clave, frozenset((clave,)))


def _nombre_herramienta_canonico(nombre: str) -> str:
    """Resuelve únicamente aliases cerrados al nombre canónico de publicación."""

    clave = clave_concepto(nombre)
    return _NOMBRES_CANONICOS_HERRAMIENTAS.get(clave, nombre.strip())


def _clave_herramienta_canonica(nombre: str) -> str:
    """Produce una clave de deduplicación común para nombre canónico y aliases cerrados."""

    return clave_concepto(_nombre_herramienta_canonico(nombre))


def _coincide_nombre_herramienta_en_texto(nombre: str, texto: str) -> bool:
    """Exige el nombre canónico o un alias cerrado como frase normalizada completa."""

    texto_normalizado = clave_concepto(texto)
    return any(
        f" {clave} " in f" {texto_normalizado} " for clave in _claves_herramienta_cerradas(nombre)
    )


def _herramienta_nueva_evidenciada(
    nombre: str,
    _evidencia_llm: str,
    caso: dict[str, object],
) -> bool:
    """Permite una herramienta nueva solo con nombre literal en evidencia estructurada."""

    clave_nombre = clave_concepto(nombre)
    if not clave_nombre or clave_nombre in _HERRAMIENTAS_GENERICAS:
        return False
    evidencias = caso.get("evidencia_herramientas_candidata")
    if evidencias is None:
        evidencias = caso.get("evidencia_herramientas")
    if not isinstance(evidencias, list):
        return False
    for item in evidencias:
        if not isinstance(item, dict):
            continue
        texto = str(item.get("texto") or "")
        if _coincide_nombre_herramienta_en_texto(nombre, texto):
            return True
    return False


def _reporte_decision(
    decision: DecisionCurricular,
    estado: str,
    problemas: list[str] | None = None,
    inspeccion: InspeccionCurricular | None = None,
    modelos_escalados: list[str] | None = None,
) -> dict[str, object]:
    fila = decision.model_dump(mode="json")
    fila.update(
        {
            "tipo": "decision_curricular",
            "estado": estado,
            "problemas": problemas or [],
            "inspeccion": inspeccion.model_dump(mode="json") if inspeccion else None,
        }
    )
    if modelos_escalados:
        fila["modelos_escalados"] = modelos_escalados
    return fila


def _cargar_perfil(carrera: str, periodo: str) -> dict[str, object]:
    return cargar_perfil_carrera(carrera, periodo)


def _hash_id(prefijo: str, *partes: str) -> str:
    payload = "|".join(clave_concepto(parte) for parte in partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _clave_lote(
    lote: tuple[dict[str, object], ...],
    perfil: dict[str, object],
    modelo: str,
) -> str:
    payload = json.dumps(
        {"lote": lote, "perfil": perfil, "modelo": modelo},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _trocear(
    valores: tuple[dict[str, object], ...],
    tamanio: int,
) -> Iterable[tuple[dict[str, object], ...]]:
    for indice in range(0, len(valores), tamanio):
        yield valores[indice : indice + tamanio]


def _leer_cache(ruta: Path) -> dict[str, dict[str, object]]:
    if not ruta.is_file():
        return {}
    resultado: dict[str, dict[str, object]] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(fila, dict) and isinstance(fila.get("clave_lote"), str):
            respuesta = fila.get("respuesta")
            if isinstance(respuesta, dict):
                resultado[fila["clave_lote"]] = respuesta
    return resultado


def _guardar_cache(ruta: Path, cache: dict[str, dict[str, object]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for clave, respuesta in sorted(cache.items()):
            archivo.write(
                json.dumps(
                    {"clave_lote": clave, "respuesta": respuesta},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def _nombre_modelo(llm: object) -> str:
    for atributo in ("model_name", "model"):
        valor = getattr(llm, atributo, "")
        if valor:
            return str(valor)
    return "desconocido"


def _confianza_minima() -> float:
    return decimal("NORMALIZADOR_CURRICULAR_MIN_CONFIDENCE", 0.72)
