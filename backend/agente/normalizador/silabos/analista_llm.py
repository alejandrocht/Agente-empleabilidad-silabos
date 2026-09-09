"""Analista semántico curricular con salida estructurada y juez local.

Python conserva la extracción y la autoridad de la evidencia. El LLM interpreta
el logro dentro del perfil de carrera; el juez de este módulo solo permite pasar
decisiones que puedan verificarse contra el sílabo y los candidatos detectados.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from agente.config.settings import (
    ConfiguracionNormalizadorCurricular,
)
from agente.llm.fabrica import obtener_llm
from agente.normalizador.embeddings import EmbeddingRetriever, EmbeddingScope
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
from agente.normalizador.silabos import contexto_analista as _contexto_analista
from agente.normalizador.silabos.contexto_curricular import (
    _CLAVES_PERFIL_NO_TRANSPORTABLES,  # noqa: F401
    construir_contexto_por_logro,
    construir_perfil_para_prompt,
)
from agente.normalizador.silabos.herramientas import (
    herramienta_nueva_evidenciada,
    nombre_herramienta_coincide,
)
from agente.normalizador.silabos.perfil_carrera import cargar_perfil_carrera
from agente.normalizador.silabos.politica_curricular import (
    MOTIVO_COMPETENCIA_GENERICA,
    es_competencia_generica,
)
from agente.observabilidad.langsmith import invocar_llm

_METODOS_RECUPERACION_AUDITABLES = _contexto_analista._METODOS_RECUPERACION_AUDITABLES
_REASON_CODES_RECUPERACION_AUDITABLES = _contexto_analista._REASON_CODES_RECUPERACION_AUDITABLES
_IDENTIFICADOR_AUDITABLE = _contexto_analista._IDENTIFICADOR_AUDITABLE
_ETIQUETA_SCOPE_AUDITABLE = _contexto_analista._ETIQUETA_SCOPE_AUDITABLE
_PERIODO_SCOPE_AUDITABLE = _contexto_analista._PERIODO_SCOPE_AUDITABLE
_FINGERPRINT_AUDITABLE = _contexto_analista._FINGERPRINT_AUDITABLE
_MARCADORES_SECRETOS = _contexto_analista._MARCADORES_SECRETOS
_RECURSOS_ENSENANZA_GENERICOS = _contexto_analista._RECURSOS_ENSENANZA_GENERICOS
_prompt_analista = _contexto_analista._prompt_analista
_perfil_semantico = _contexto_analista._perfil_semantico
_propuesta_semantica = _contexto_analista._propuesta_semantica
_payload_semantico_lote = _contexto_analista._payload_semantico_lote
_competencias_semanticas = _contexto_analista._competencias_semanticas
_temas_programa_semanticos = _contexto_analista._temas_programa_semanticos
_casos_curriculares = _contexto_analista._casos_curriculares
_auditoria_contexto = _contexto_analista._auditoria_contexto
_recuperacion_auditable_por_logro = _contexto_analista._recuperacion_auditable_por_logro
_texto_auditable = _contexto_analista._texto_auditable
_modelo_auditable = _contexto_analista._modelo_auditable
_fingerprint_auditable = _contexto_analista._fingerprint_auditable
_configuracion_auditable = _contexto_analista._configuracion_auditable
_etiqueta_scope_auditable = _contexto_analista._etiqueta_scope_auditable
_periodo_scope_auditable = _contexto_analista._periodo_scope_auditable
_minimum_similarity_auditable = _contexto_analista._minimum_similarity_auditable
_scope_recuperacion_auditable = _contexto_analista._scope_recuperacion_auditable
_evidencias_programa_analitico = _contexto_analista._evidencias_programa_analitico
_deduplicar_evidencias_herramientas = _contexto_analista._deduplicar_evidencias_herramientas
_programa_es_recurso_no_evidenciable = _contexto_analista._programa_es_recurso_no_evidenciable


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

    decisiones: list[DecisionCurricular] = Field(default_factory=list)


class DecisionCurricularLLM(BaseModel):
    """Respuesta de transporte del analista, correlacionada por orden en Python."""

    logro: str = Field(min_length=2, max_length=2000)
    competencia: ConceptoPropuesto
    habilidad: ConceptoPropuesto
    herramientas: list[HerramientaPropuesta] = Field(default_factory=list, max_length=8)
    evidencia: list[str] = Field(default_factory=list, max_length=6)
    justificacion: str = Field(default="", max_length=1200)
    confianza: float = Field(ge=0, le=1)
    requiere_revision: bool = False

    @model_validator(mode="before")
    @classmethod
    def _aceptar_decision_interna_en_pruebas(cls, valor: object) -> object:
        """Permite adaptar fixtures/cache internos sin ampliar el esquema LLM."""

        if isinstance(valor, DecisionCurricular):
            data = valor.model_dump(exclude={"id_habilidad_fuente"})
            evidencia = data.get("evidencia") or []
            data["logro"] = (
                str(evidencia[0])
                if isinstance(evidencia, list) and evidencia and evidencia[0]
                else str(data.get("habilidad", {}).get("nombre") or "")
            )
            return data
        if isinstance(valor, Mapping):
            data = dict(valor)
            if not data.get("logro") and data.get("logro_fuente"):
                data["logro"] = data["logro_fuente"]
            return data
        return valor


class LoteDecisionesCurricularesLLM(BaseModel):
    """Contrato de salida externo: una decisión por logro, en el mismo orden."""

    decisiones: list[DecisionCurricularLLM] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResultadoAnalisisCurricular:
    """Propuestas pendientes y evidencia auditable del analista."""

    reportes: tuple[dict[str, object], ...]
    modelo_analista: str
    lotes: int
    # Compatibility-only fields for historical report/API readers; no residual execution.
    modelo_analista_residual: str = "no_ejecutado"
    decisiones_escaladas: int = 0
    auditoria_contexto: dict[str, object] | None = None
    progreso: ProgresoLimpiezaLLM | None = None
    propuestas: dict[str, DecisionCurricular] = field(default_factory=dict)


_ANCLAS_NO_SEMANTICAS = frozenset(
    {
        "para",
        "desde",
        "sobre",
        "entre",
        "mediante",
        "nivel",
        "forma",
        "proceso",
        "procesos",
        "profesional",
        "profesionales",
        "curricular",
        "curriculares",
    }
)


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
_HABILIDADES_GENERICAS = {
    "comunicar",
    "integrar",
    "aplicar conceptos",
    "usar herramientas",
    "analizar información",
}
def analizar_registros_curriculares(
    registros: list[dict[str, object]],
    catalogo: CatalogoCHH,
    carrera: str,
    periodo: str,
    directorio_ejecucion: Path,
    *,
    al_actualizar_progreso: Callable[[ProgresoLimpiezaLLM], None] | None = None,
    progreso_inicial: ProgresoLimpiezaLLM | None = None,
    id_ejecucion: str = "",
    cancelada: Callable[[], bool] | None = None,
    embedding_retriever: EmbeddingRetriever | None = None,
    embedding_scope: EmbeddingScope | None = None,
    limites_candidatos: Mapping[str, int] | None = None,
    pool_retrieval: int | None = None,
    configuracion_curricular: ConfiguracionNormalizadorCurricular | None = None,
) -> ResultadoAnalisisCurricular:
    """Analiza todos los logros fuente y conserva fallos sin abortar el lote."""

    def verificar_cancelacion() -> None:
        """Evita iniciar otra llamada LLM después de una cancelación."""

        if cancelada is not None and cancelada():
            raise CancelacionSolicitada()

    verificar_cancelacion()
    if configuracion_curricular is None:
        raise ValueError("El analista curricular requiere configuracion_curricular de la ejecución")
    configuracion = configuracion_curricular
    limites_contexto = (
        configuracion.limites_embedding() if limites_candidatos is None else limites_candidatos
    )
    limites_lexicales = (
        configuracion.limites_lexicales() if limites_candidatos is None else limites_candidatos
    )

    perfil = _cargar_perfil(carrera, periodo)
    contexto_perfil = construir_contexto_por_logro(
        {},
        catalogo,
        perfil,
        limites_candidatos=limites_contexto,
        limites_lexicales=limites_lexicales,
        limite_ejemplos=configuracion.limite_ejemplos_contexto,
    )
    perfil_prompt = construir_perfil_para_prompt(perfil)
    casos = tuple(
        _casos_curriculares(
            registros,
            catalogo,
            perfil,
            retriever=embedding_retriever,
            embedding_scope=embedding_scope,
            limites_candidatos=limites_contexto,
            limites_lexicales=limites_lexicales,
            pool_retrieval=pool_retrieval,
            limite_ejemplos=configuracion.limite_ejemplos_contexto,
            crear_id_habilidad=_hash_id,
        )
    )
    auditoria_contexto = _auditoria_contexto(casos, contexto_perfil)
    lotes = tuple(_trocear_por_silabo(casos, configuracion.tamano_lote_llm))
    cache_path = directorio_ejecucion / "salidas" / "reportes" / "decisiones_llm_cache.jsonl"
    cache = _leer_cache(cache_path)
    analista = obtener_llm("analista_curricular", configuracion_curricular=configuracion)
    modelo_analista = _nombre_modelo(analista)
    propuestas: dict[str, DecisionCurricular] = {}
    reportes: list[dict[str, object]] = []
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
                decision = _normalizar_habilidad(decision, perfil)
                errores = _validar_decision(decision, caso)
                if errores:
                    reportes.append(_reporte_decision(decision, "REVISAR_VALIDACION", errores))
                    continue
                propuestas[decision.id_habilidad_fuente] = decision
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

    for decision in propuestas.values():
        reportes.append(
            _reporte_decision(
                decision,
                "PENDIENTE_REVISION_HUMANA",
                ["PROPUESTA_LLM_REQUIERE_DECISION_HUMANA"],
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
        propuestas=propuestas,
        reportes=tuple(reportes),
        modelo_analista=modelo_analista,
        lotes=len(lotes),
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
    id_ejecucion: str = "",
    chunk: int | None = None,
    reintento: bool = False,
) -> LoteDecisionesCurriculares:
    prompt = _prompt_analista(lote, perfil_prompt, carrera, periodo)
    estructurado = llm.with_structured_output(LoteDecisionesCurricularesLLM)  # type: ignore[attr-defined]
    respuesta = invocar_llm(
        estructurado,
        prompt,
        rol="analista_curricular",
        id_ejecucion=id_ejecucion,
        carrera=carrera,
        periodo=periodo,
        chunk=chunk,
        reintento=reintento,
    )
    if isinstance(respuesta, LoteDecisionesCurriculares):
        return respuesta
    respuesta_llm = LoteDecisionesCurricularesLLM.model_validate(respuesta)
    if len(respuesta_llm.decisiones) != len(lote):
        return _asignar_decisiones_parciales_por_logro(lote, respuesta_llm)
    return _asignar_decisiones_por_orden(lote, respuesta_llm)


def _asignar_decisiones_por_orden(
    lote: tuple[dict[str, object], ...],
    respuesta: LoteDecisionesCurricularesLLM,
) -> LoteDecisionesCurriculares:
    """Restaura el linaje interno usando el orden estable de entrada/salida."""

    _validar_respuesta_por_orden(
        lote,
        respuesta.decisiones,
        exigir_logro=True,
        nombre="decisiones",
    )
    decisiones: list[DecisionCurricular] = []
    for caso, decision in zip(lote, respuesta.decisiones, strict=True):
        materializada = _materializar_decision(caso, decision)
        if materializada is not None:
            decisiones.append(materializada)
    return LoteDecisionesCurriculares(decisiones=decisiones)


def _materializar_decision(
    caso: Mapping[str, object],
    decision: DecisionCurricularLLM,
) -> DecisionCurricular | None:
    id_habilidad = str(caso.get("id_habilidad_fuente") or "")
    if not id_habilidad:
        return None
    return DecisionCurricular(
        id_habilidad_fuente=id_habilidad,
        competencia=decision.competencia,
        habilidad=decision.habilidad,
        herramientas=decision.herramientas,
        evidencia=decision.evidencia,
        justificacion=decision.justificacion,
        confianza=decision.confianza,
        requiere_revision=decision.requiere_revision,
    )


def _asignar_decisiones_parciales_por_logro(
    lote: tuple[dict[str, object], ...],
    respuesta: LoteDecisionesCurricularesLLM,
) -> LoteDecisionesCurriculares:
    """Mapea una respuesta parcial solo si cada logro literal identifica su caso."""

    casos_por_logro: dict[str, dict[str, object]] = {}
    for caso in lote:
        clave = _clave_logro_literal(caso.get("logro"))
        if not clave or clave in casos_por_logro:
            raise ValueError("No se puede identificar de forma única un logro del lote.")
        casos_por_logro[clave] = caso

    decisiones: list[DecisionCurricular] = []
    claves_usadas: set[str] = set()
    for decision in respuesta.decisiones:
        clave = _clave_logro_literal(decision.logro)
        caso = casos_por_logro.get(clave)
        if caso is None or clave in claves_usadas:
            raise ValueError("La respuesta parcial contiene un logro ausente o duplicado del lote.")
        claves_usadas.add(clave)
        materializada = _materializar_decision(caso, decision)
        if materializada is not None:
            decisiones.append(materializada)
    return LoteDecisionesCurriculares(decisiones=decisiones)


def _validar_respuesta_por_orden(
    lote: tuple[dict[str, object], ...],
    respuesta: Iterable[object],
    *,
    exigir_logro: bool,
    nombre: str,
) -> None:
    """Evita asignar una respuesta LLM a un ID distinto por omisión o reordenamiento."""

    respuestas = tuple(respuesta)
    if len(respuestas) != len(lote):
        raise ValueError(
            f"La cardinalidad de la respuesta de {nombre} es {len(respuestas)} "
            f"elementos para {len(lote)} casos."
        )

    logros_respuesta = [str(getattr(item, "logro", "") or "").strip() for item in respuestas]
    for indice, (caso, logro_respuesta) in enumerate(zip(lote, logros_respuesta, strict=True), 1):
        logro_esperado = str(caso.get("logro") or "").strip()
        if not logro_respuesta:
            raise ValueError(
                f"La respuesta de {nombre} no devolvió el logro literal del caso {indice}."
            )
        if _clave_logro_literal(logro_respuesta) != _clave_logro_literal(logro_esperado):
            raise ValueError(f"La respuesta de {nombre} no conserva el orden del caso {indice}.")


def _clave_logro_literal(valor: object) -> str:
    """Normaliza únicamente Unicode y espacios; conserva puntuación y palabras."""

    texto = unicodedata.normalize("NFKC", str(valor or "")).replace(" ", " ")
    return re.sub(r"\s+", " ", texto).strip().casefold()


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
    elif es_competencia_generica(decision.competencia.nombre):
        errores.append(MOTIVO_COMPETENCIA_GENERICA)
    fuente_completa = " ".join(
        str(caso.get(campo) or "")
        for campo in ("curso", "sumilla", "logro_general", "logro", "contenido_relacionado")
    )
    fuente_clave = clave_concepto(fuente_completa)
    if not _competencia_anclada_en_fuente_o_declarada(
        decision.competencia.nombre,
        fuente_clave,
        caso,
    ):
        errores.append("COMPETENCIA_SIN_ANCLA_FUENTE")
    evidencias = evidencia_decision(decision)
    evidencias_en_fuente = [
        evidencia for evidencia in evidencias if _evidencia_en_texto(evidencia, fuente_clave)
    ]
    if not evidencias:
        errores.append("SIN_EVIDENCIA_LLM")
    elif not evidencias_en_fuente:
        errores.append("EVIDENCIA_NO_ENCONTRADA")
    else:
        errores.extend(_errores_grounding_decision(decision, evidencias_en_fuente))
    herramientas_detectadas = caso.get("herramientas_detectadas")
    if not isinstance(herramientas_detectadas, list):
        herramientas_detectadas = []
    disponibles = {clave_concepto(str(nombre)) for nombre in herramientas_detectadas}
    for herramienta in decision.herramientas:
        herramienta_existente = nombre_herramienta_coincide(herramienta.nombre, disponibles)
        herramienta_nueva = herramienta_nueva_evidenciada(
            herramienta.nombre, herramienta.evidencia, caso
        )
        if not herramienta_existente and not herramienta_nueva:
            errores.append(f"HERRAMIENTA_NO_DETECTADA:{herramienta.nombre}")
    return errores


def _errores_grounding_decision(
    decision: DecisionCurricular,
    evidencias: list[str],
) -> list[str]:
    """Verify that one literal syllabus quote anchors the proposed skill.

    A valid quote alone is insufficient: the skill must share at least two
    normalized content anchors with one cited fragment (or all anchors when it
    has fewer than two). A competence may be broader than the skill, but its
    lexical relation can only add diagnostic context; it never substitutes the
    syllabus evidence that anchors the skill.
    """

    habilidad = _anclas_grounding(decision.habilidad.nombre)
    competencia = _anclas_grounding(decision.competencia.nombre)
    minimas_habilidad = min(2, len(habilidad))
    habilidad_anclada = any(
        len(habilidad & _anclas_grounding(evidencia)) >= minimas_habilidad
        for evidencia in evidencias
    )
    errores: list[str] = []
    if not habilidad or not habilidad_anclada:
        errores.append("HABILIDAD_SIN_ANCLA_EVIDENCIA")
        if not competencia or not (competencia & habilidad):
            errores.append("COMPETENCIA_SIN_ANCLA_HABILIDAD")
    return errores


def _anclas_grounding(texto: str) -> set[str]:
    """Reduce texto a raíces conservadoras, evitando conectores y etiquetas vagas."""

    return {
        token[:5]
        for token in clave_concepto(texto).split()
        if len(token) >= 3 and token not in _ANCLAS_NO_SEMANTICAS
    }


def _competencia_anclada_en_fuente_o_declarada(
    competencia: str,
    fuente_normalizada: str,
    caso: dict[str, object],
) -> bool:
    """Require the competence to be source-grounded or explicitly declared."""

    anclas_competencia = _anclas_grounding(competencia)
    if anclas_competencia & _anclas_grounding(fuente_normalizada):
        return True
    declaraciones = caso.get("competencias_declaradas")
    if not isinstance(declaraciones, list):
        return False
    clave_competencia = clave_concepto(competencia)
    if not clave_competencia:
        return False
    for declaracion in declaraciones:
        if isinstance(declaracion, dict):
            nombre = str(declaracion.get("nombre") or "")
        else:
            nombre = str(declaracion or "")
        if clave_concepto(nombre) == clave_competencia:
            return True
    return False


def _reporte_sin_decision_llm(
    caso: dict[str, object],
) -> dict[str, object]:
    """Registra un logro que el analista no representó, sin fabricar una decisión."""

    reporte: dict[str, object] = {
        "tipo": "decision_curricular",
        "estado": "REVISAR_SIN_DECISION_LLM",
        "id_habilidad_fuente": str(caso["id_habilidad_fuente"]),
        "problemas": ["SIN_DECISION_LLM"],
    }
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

    if evidencia_decision(decision):
        return decision
    logro = str(caso.get("logro") or "").strip()
    if not logro:
        return decision
    return decision.model_copy(update={"evidencia": [logro]})


def evidencia_decision(decision: DecisionCurricular) -> list[str]:
    """Devuelve las citas declaradas por el analista sin duplicarlas."""

    citas: list[str] = []
    for valor in decision.evidencia:
        texto = str(valor or "").strip()
        if texto and texto not in citas:
            citas.append(texto)
    return citas


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
    perfil: Mapping[str, object] | None,
) -> DecisionCurricular:
    """Aplica únicamente equivalencias explícitas del perfil de carrera."""

    nombre = decision.habilidad.nombre
    reglas = perfil.get("normalizaciones_habilidad") if isinstance(perfil, Mapping) else None
    if not isinstance(reglas, Mapping):
        return decision
    reemplazo = next(
        (
            str(valor).strip()
            for origen, valor in reglas.items()
            if clave_concepto(origen) == clave_concepto(nombre) and str(valor).strip()
        ),
        None,
    )
    if reemplazo is None:
        return decision
    if nombre[:1].islower():
        reemplazo = reemplazo[:1].lower() + reemplazo[1:]
    habilidad = decision.habilidad.model_copy(update={"nombre": reemplazo})
    return decision.model_copy(update={"habilidad": habilidad})


def _normalizar_habilidad(
    decision: DecisionCurricular,
    perfil: Mapping[str, object] | None = None,
) -> DecisionCurricular:
    """Normaliza formas globales y equivalencias explícitas del perfil."""

    decision = _normalizar_habilidad_forma_conjugada(decision)
    decision = _normalizar_habilidad_nominalizada(decision)
    return _normalizar_habilidad_frase_cerrada(decision, perfil)


def _evidencia_en_texto(fragmento: str, fuente_normalizada: str) -> bool:
    evidencia = clave_concepto(fragmento)
    if len(evidencia) < 3:
        return False
    if evidencia in fuente_normalizada:
        return True
    tokens = set(evidencia.split())
    return len(tokens & set(fuente_normalizada.split())) / len(tokens) >= 0.75


def _reporte_decision(
    decision: DecisionCurricular,
    estado: str,
    problemas: list[str] | None = None,
) -> dict[str, object]:
    fila = decision.model_dump(mode="json")
    fila.update(
        {
            "tipo": "decision_curricular",
            "estado": estado,
            "problemas": problemas or [],
        }
    )
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


def _trocear_por_silabo(
    valores: tuple[dict[str, object], ...],
    tamanio: int,
) -> Iterable[tuple[dict[str, object], ...]]:
    """No parte un sílabo: su contexto semántico debe viajar una sola vez."""

    lote: list[dict[str, object]] = []
    grupos: dict[str, list[dict[str, object]]] = {}
    orden: list[str] = []
    for indice, valor in enumerate(valores):
        clave = str(valor.get("id_silabo") or f"orden-{indice}")
        if clave not in grupos:
            grupos[clave] = []
            orden.append(clave)
        grupos[clave].append(valor)
    for clave in orden:
        grupo = grupos[clave]
        if lote and len(lote) + len(grupo) > tamanio:
            yield tuple(lote)
            lote = []
        lote.extend(grupo)
    if lote:
        yield tuple(lote)


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
