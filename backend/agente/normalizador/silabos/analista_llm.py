"""Analista semántico curricular con salida estructurada y juez local.

Python conserva la extracción y la autoridad de la evidencia. El LLM interpreta
el logro dentro del perfil de carrera; el juez de este módulo solo permite pasar
decisiones que puedan verificarse contra el sílabo y los candidatos detectados.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from agente.config.settings import (
    ConfiguracionNormalizadorCurricular,
)
from agente.llm.fabrica import obtener_llm
from agente.normalizador.embeddings import EmbeddingRetriever, EmbeddingScope
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.identidad import hashed
from agente.normalizador.modelos import (
    EstadoReporteFinalLLM,
    FaseProgresoLLM,
    ProgresoLimpiezaLLM,
    UltimoChunkLimpiezaLLM,
)
from agente.normalizador.silabos import contexto_analista as _contexto_analista
from agente.normalizador.silabos import normalizacion_decisiones as _normalizacion_decisiones
from agente.normalizador.silabos import respuesta_cache_analista as _respuesta_cache_analista
from agente.normalizador.silabos.contexto_curricular import (
    _CLAVES_PERFIL_NO_TRANSPORTABLES,  # noqa: F401
    construir_contexto_por_logro,
    construir_perfil_para_prompt,
)
from agente.normalizador.silabos.perfil_carrera import cargar_perfil_carrera
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
_ANCLAS_NO_SEMANTICAS = _normalizacion_decisiones._ANCLAS_NO_SEMANTICAS
_VERBOS_HABILIDAD = _normalizacion_decisiones._VERBOS_HABILIDAD
_FORMAS_CONJUGADAS_HABILIDAD = _normalizacion_decisiones._FORMAS_CONJUGADAS_HABILIDAD
_NOMINALIZACIONES_HABILIDAD = _normalizacion_decisiones._NOMINALIZACIONES_HABILIDAD
_HABILIDADES_GENERICAS = _normalizacion_decisiones._HABILIDADES_GENERICAS
_validar_decision = _normalizacion_decisiones._validar_decision
_errores_grounding_decision = _normalizacion_decisiones._errores_grounding_decision
_anclas_grounding = _normalizacion_decisiones._anclas_grounding
_competencia_anclada_en_fuente_o_declarada = (
    _normalizacion_decisiones._competencia_anclada_en_fuente_o_declarada
)
_reporte_sin_decision_llm = _normalizacion_decisiones._reporte_sin_decision_llm
_reporte_reintento_omitidos = _normalizacion_decisiones._reporte_reintento_omitidos
_asegurar_cobertura_reportes = _normalizacion_decisiones._asegurar_cobertura_reportes
_completar_evidencia = _normalizacion_decisiones._completar_evidencia
evidencia_decision = _normalizacion_decisiones.evidencia_decision
_normalizar_habilidad_nominalizada = _normalizacion_decisiones._normalizar_habilidad_nominalizada
_normalizar_habilidad_forma_conjugada = (
    _normalizacion_decisiones._normalizar_habilidad_forma_conjugada
)
_normalizar_habilidad_frase_cerrada = _normalizacion_decisiones._normalizar_habilidad_frase_cerrada
_normalizar_habilidad = _normalizacion_decisiones._normalizar_habilidad
_evidencia_en_texto = _normalizacion_decisiones._evidencia_en_texto
_reporte_decision = _normalizacion_decisiones._reporte_decision
_validar_respuesta_por_orden = _respuesta_cache_analista._validar_respuesta_por_orden
_clave_logro_literal = _respuesta_cache_analista._clave_logro_literal
_clave_lote = _respuesta_cache_analista._clave_lote
_version_prompt_analista = _contexto_analista.version_prompt_analista
_leer_cache = _respuesta_cache_analista._leer_cache
_guardar_cache = _respuesta_cache_analista._guardar_cache
_nombre_modelo = _respuesta_cache_analista._nombre_modelo


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
            crear_id_habilidad=hashed,
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
        clave_lote = _clave_lote(lote, perfil, modelo_analista, _version_prompt_analista())
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
            clave_reintento = f"reintento:{_clave_lote(lote_reintento, perfil, modelo_analista, _version_prompt_analista())}"
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
    return LoteDecisionesCurriculares(
        decisiones=_respuesta_cache_analista._asignar_decisiones_por_orden(
            lote,
            respuesta,
            materializar_decision=_materializar_decision,
        )
    )


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
    return LoteDecisionesCurriculares(
        decisiones=_respuesta_cache_analista._asignar_decisiones_parciales_por_logro(
            lote,
            respuesta,
            materializar_decision=_materializar_decision,
        )
    )


def _cargar_perfil(carrera: str, periodo: str) -> dict[str, object]:
    return cargar_perfil_carrera(carrera, periodo)


# `_hash_id` stays bound for the callers that reach it by name (the
# curricular test suite and `resolucion_curricular`'s seam); it is now only a
# name for the shared helper.
_hash_id = hashed


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
