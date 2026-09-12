"""Pruebas del contrato LLM curricular sin llamadas de red."""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
from pathlib import Path
from threading import Event

import pytest

from agente.config import settings
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import ProgresoLimpiezaLLM
from agente.normalizador.silabos import (
    analista_llm,
    contexto_analista,
    normalizacion_decisiones,
    respuesta_cache_analista,
    salida,
)


class _LLMFalso:
    model_name = "gpt-5.6-sol-test"

    def __init__(self) -> None:
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _prompt: str):
        assert self._schema is not None
        return self._schema(
            decisiones=[
                analista_llm.DecisionCurricular(
                    id_habilidad_fuente=analista_llm._hash_id(
                        "HAB_SRC", "SIL_1", "1", "Diseñar campañas de marketing"
                    ),
                    competencia=analista_llm.ConceptoPropuesto(
                        nombre="Gestión de campañas de marketing",
                        descripcion="Planificación y gestión de campañas de marketing.",
                        tipo="dura",
                    ),
                    habilidad=analista_llm.ConceptoPropuesto(
                        nombre="Diseñar campañas de marketing",
                        descripcion="Diseño de campañas de marketing.",
                        tipo="habilidad",
                    ),
                    evidencia=["Diseñar campañas de marketing"],
                    confianza=0.94,
                )
            ]
        )


@pytest.fixture(autouse=True)
def _inyectar_snapshot_curricular(monkeypatch: pytest.MonkeyPatch) -> None:
    original = analista_llm.analizar_registros_curriculares

    def analizar_con_snapshot(*args: object, **kwargs: object):
        kwargs.setdefault(
            "configuracion_curricular",
            settings.configuracion_normalizador_curricular(),
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(analista_llm, "analizar_registros_curriculares", analizar_con_snapshot)


def _catalogo_vacio() -> CatalogoCHH:
    return CatalogoCHH(
        competencias=(),
        habilidades=(),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def _registros_para(
    logro: str,
    *,
    programa_analitico: list[str] | None = None,
    herramientas_evidencia: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    return [
        {
            "id_silabo": "SIL_1",
            "origen": {"archivo": "marketing.docx"},
            "datos": {
                "curso": "Campañas",
                "sumilla": logro,
                "logro_general": logro,
                "texto_relevante": "Contexto de marketing.",
                "logros_especificos": [{"orden": "1", "descripcion": logro}],
                "competencias_declaradas": [],
                "programa_analitico": programa_analitico or [],
                "herramientas_evidencia": herramientas_evidencia or [],
            },
        }
    ]


class _LLMDecisionesFalso:
    def __init__(self, modelo: str, decision: analista_llm.DecisionCurricular) -> None:
        self.model_name = modelo
        self._decision = decision
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _prompt: str):
        assert self._schema is analista_llm.LoteDecisionesCurricularesLLM
        return self._schema(decisiones=[self._decision])


class _LLMLoteDecisionesFalso:
    def __init__(
        self,
        modelo: str,
        decisiones: list[analista_llm.DecisionCurricular],
    ) -> None:
        self.model_name = modelo
        self._decisiones = decisiones
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _prompt: str):
        assert self._schema is analista_llm.LoteDecisionesCurricularesLLM
        return self._schema(decisiones=self._decisiones)


class _LLMLoteSecuencialFalso:
    def __init__(
        self,
        modelo: str,
        respuestas: list[list[analista_llm.DecisionCurricular]],
    ) -> None:
        self.model_name = modelo
        self._respuestas = iter(respuestas)
        self._schema = None
        self.logros_por_llamada: list[list[str]] = []

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, prompt: str):
        assert self._schema is analista_llm.LoteDecisionesCurricularesLLM
        contextos = json.loads(prompt.split("CASOS:\n", maxsplit=1)[1])
        self.logros_por_llamada.append(
            [logro for contexto in contextos for logro in contexto["logros_especificos"]]
        )
        return self._schema(decisiones=next(self._respuestas))


def _decision_para(
    logro: str,
    **cambios: object,
) -> analista_llm.DecisionCurricular:
    decision = analista_llm.DecisionCurricular(
        id_habilidad_fuente=analista_llm._hash_id("HAB_SRC", "SIL_1", "1", logro),
        competencia=analista_llm.ConceptoPropuesto(nombre="Gestión de campañas"),
        habilidad=analista_llm.ConceptoPropuesto(nombre=logro),
        evidencia=[logro],
        confianza=0.94,
    )
    return decision.model_copy(update=cambios)


def _decision_para_orden(
    logro: str,
    orden: str,
    **cambios: object,
) -> analista_llm.DecisionCurricular:
    decision = _decision_para(logro).model_copy(
        update={"id_habilidad_fuente": analista_llm._hash_id("HAB_SRC", "SIL_1", orden, logro)}
    )
    return decision.model_copy(update=cambios)


def _catalogo_con_herramientas(*herramientas: str) -> CatalogoCHH:
    return CatalogoCHH(
        competencias=(),
        habilidades=(),
        herramientas=tuple(
            ConceptoCHH(nombre.upper().replace(" ", "_"), nombre, "Herramienta")
            for nombre in herramientas
        ),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="test",
    )


def test_contexto_analista_reexporta_helpers_y_preserva_modelos_y_prompt() -> None:
    for nombre in (
        "_prompt_analista",
        "_perfil_semantico",
        "_propuesta_semantica",
        "_payload_semantico_lote",
        "_casos_curriculares",
        "_auditoria_contexto",
        "_scope_recuperacion_auditable",
        "_evidencias_programa_analitico",
        "_deduplicar_evidencias_herramientas",
    ):
        assert getattr(analista_llm, nombre) is getattr(contexto_analista, nombre)

    for nombre in (
        "_validar_decision",
        "_errores_grounding_decision",
        "_anclas_grounding",
        "_competencia_anclada_en_fuente_o_declarada",
        "_reporte_sin_decision_llm",
        "_reporte_reintento_omitidos",
        "_asegurar_cobertura_reportes",
        "_completar_evidencia",
        "evidencia_decision",
        "_normalizar_habilidad_nominalizada",
        "_normalizar_habilidad_forma_conjugada",
        "_normalizar_habilidad_frase_cerrada",
        "_normalizar_habilidad",
        "_evidencia_en_texto",
        "_reporte_decision",
    ):
        assert getattr(analista_llm, nombre) is getattr(normalizacion_decisiones, nombre)

    for nombre in (
        "_validar_respuesta_por_orden",
        "_clave_logro_literal",
        "_clave_lote",
        "_leer_cache",
        "_guardar_cache",
        "_nombre_modelo",
    ):
        assert getattr(analista_llm, nombre) is getattr(respuesta_cache_analista, nombre)

    assert "DecisionCurricular" not in normalizacion_decisiones.__dict__
    assert "agente" not in Path(respuesta_cache_analista.__file__).read_text(encoding="utf-8")
    assert tuple(inspect.signature(analista_llm._asignar_decisiones_por_orden).parameters) == (
        "lote",
        "respuesta",
    )
    assert tuple(
        inspect.signature(analista_llm._asignar_decisiones_parciales_por_logro).parameters
    ) == ("lote", "respuesta")
    assert analista_llm.DecisionCurricular.__module__ == analista_llm.__name__
    assert analista_llm.LoteDecisionesCurricularesLLM.__module__ == analista_llm.__name__
    assert (
        analista_llm.LoteDecisionesCurricularesLLM.model_json_schema()["properties"]["decisiones"][
            "type"
        ]
        == "array"
    )
    lote = (
        {
            "id_silabo": "SIL_GOLD",
            "curso": "Analítica",
            "sumilla": "Decisiones con evidencia.",
            "logro_general": "Sustentar decisiones.",
            "logro": "Analizar datos para sustentar decisiones.",
            "competencias_declaradas": [
                {"nombre": "Razonamiento analítico", "descripcion": "Evalúa evidencia."}
            ],
            "programa_analitico": ["Semana 1 | Datos | Power BI"],
            "programa_analitico_detalle": [],
        },
    )
    prompt = analista_llm._prompt_analista(
        lote,
        {"reglas": ["Usar evidencia."], "hash": "no-viaja"},
        "ANALITICA",
        "2026-1",
    )
    assert hashlib.sha256(prompt.encode()).hexdigest() == (
        "0b32b4fbc85576091aee274ab9014f29b65cfbd18330f6d06cd8a2cff1e2abdf"
    )
    assert "Python" in prompt and "SAP" in prompt
    assert "Ningún logro puede quedar sin habilidad ni competencia" in prompt


def test_analista_valido_genera_propuesta_pendiente_de_revision_humana(
    monkeypatch,
    tmp_path: Path,
) -> None:
    analista = _LLMFalso()
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda *_args, **_kwargs: analista)
    registros = [
        {
            "id_silabo": "SIL_1",
            "origen": {"archivo": "marketing.docx"},
            "datos": {
                "curso": "Campañas",
                "sumilla": "Diseño de campañas de marketing.",
                "logro_general": "Diseñar campañas de marketing.",
                "texto_relevante": "Segmentación y planificación.",
                "logros_especificos": [
                    {"orden": "1", "descripcion": "Diseñar campañas de marketing"}
                ],
                "competencias_declaradas": [],
                "herramientas_evidencia": [],
            },
        }
    ]

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert resultado.modelo_analista == "gpt-5.6-sol-test"
    assert len(resultado.propuestas) == 1
    assert any(
        fila["estado"] == "PENDIENTE_REVISION_HUMANA" and fila["confianza"] == 0.94
        for fila in resultado.reportes
    )


def test_cancelacion_no_envia_un_segundo_lote_llm(monkeypatch, tmp_path: Path) -> None:
    """La bandera se evalúa antes del siguiente lote de ocho logros."""

    registros = [
        {
            "id_silabo": f"SIL_{indice}",
            "origen": {"archivo": f"curso-{indice}.docx"},
            "datos": {
                "curso": "Campañas",
                "sumilla": "Diseñar campañas de marketing.",
                "logro_general": "Diseñar campañas de marketing.",
                "texto_relevante": "Contexto de marketing.",
                "logros_especificos": [{"orden": "1", "descripcion": f"Diseñar campaña {indice}"}],
                "competencias_declaradas": [],
                "programa_analitico": [],
                "herramientas_evidencia": [],
            },
        }
        for indice in range(9)
    ]
    cancelada = Event()

    class LLMContador:
        model_name = "modelo-test"

        def __init__(self) -> None:
            self.llamadas = 0
            self.esquema = None

        def with_structured_output(self, esquema):
            self.esquema = esquema
            return self

        def invoke(self, _prompt: str):
            self.llamadas += 1
            cancelada.set()
            return self.esquema(decisiones=[])

    llm = LLMContador()
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: llm)

    with pytest.raises(CancelacionSolicitada):
        analista_llm.analizar_registros_curriculares(
            registros,
            _catalogo_vacio(),
            "Marketing",
            "2026-1",
            tmp_path,
            cancelada=cancelada.is_set,
        )

    assert llm.llamadas == 1


def test_normaliza_habilidad_nominalizada_antes_de_validarla(monkeypatch, tmp_path: Path) -> None:
    class LLMNominalizado(_LLMFalso):
        def invoke(self, _prompt: str):
            assert self._schema is not None
            id_habilidad = analista_llm._hash_id(
                "HAB_SRC", "SIL_1", "1", "Evaluación de campañas de marketing"
            )
            return self._schema(
                decisiones=[
                    analista_llm.DecisionCurricular(
                        id_habilidad_fuente=id_habilidad,
                        competencia=analista_llm.ConceptoPropuesto(
                            nombre="Gestión de campañas de marketing"
                        ),
                        habilidad=analista_llm.ConceptoPropuesto(
                            nombre="Evaluación de campañas de marketing",
                            descripcion="Descripción sin cambios.",
                            tipo="habilidad",
                        ),
                        evidencia=["Evaluación de campañas de marketing"],
                        justificacion="Justificación sin cambios.",
                        confianza=0.93,
                    )
                ]
            )

    analista = LLMNominalizado()
    monkeypatch.setattr(
        analista_llm,
        "obtener_llm",
        lambda _rol, **_kwargs: analista,
    )
    registros = [
        {
            "id_silabo": "SIL_1",
            "origen": {"archivo": "marketing.docx"},
            "datos": {
                "curso": "Campañas",
                "sumilla": "Evaluación de campañas de marketing.",
                "logro_general": "Evaluación de campañas de marketing.",
                "texto_relevante": "Métricas de campaña.",
                "logros_especificos": [
                    {"orden": "1", "descripcion": "Evaluación de campañas de marketing"}
                ],
                "competencias_declaradas": [],
                "herramientas_evidencia": [],
            },
        }
    ]

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    decision = next(iter(resultado.propuestas.values()))
    assert decision.habilidad.nombre == "Evaluar campañas de marketing"
    assert decision.habilidad.descripcion == "Descripción sin cambios."
    assert decision.habilidad.tipo == "habilidad"
    assert decision.evidencia == ["Evaluación de campañas de marketing"]
    assert decision.justificacion == "Justificación sin cambios."


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        (
            "Estructurar sistemas de costos",
            "Estructurar sistemas de costos",
        ),
        (
            "Evalúa cambios estructurales del sistema comercial global",
            "Evaluar cambios estructurales del sistema comercial global",
        ),
        (
            "Implementación de estrategias de branding",
            "Implementar estrategias de branding",
        ),
        (
            "Planificación y ejecución estratégica de negociaciones",
            "Planificar y ejecutar negociaciones estratégicas",
        ),
        (
            "Estimación y predicción multivariante",
            "Estimar y predecir fenómenos de marketing mediante métodos multivariantes",
        ),
        (
            "Elaboración y seguimiento de cronogramas de proyectos",
            "Elaborar y seguir cronogramas de proyectos",
        ),
        (
            "Procesamiento y tabulación de datos de mercado",
            "Procesar y tabular datos de mercado",
        ),
        (
            "Diagnóstico y delimitación de problemas de investigación de mercados",
            "Diagnosticar y delimitar problemas de investigación de mercados",
        ),
        (
            "Ejecución y selección de conceptos creativos",
            "Ejecutar y seleccionar conceptos creativos",
        ),
        (
            "Evaluación del aporte de promociones BTL a la cadena de valor",
            "Evaluar el aporte de promociones BTL a la cadena de valor",
        ),
    ],
)
def test_normaliza_residuales_deterministas_en_seam_publico(
    nombre: str,
    esperado: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logro = nombre
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            habilidad=analista_llm.ConceptoPropuesto(nombre=nombre),
        ),
    )
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    decision = next(iter(resultado.propuestas.values()))
    assert decision.habilidad.nombre == esperado
    assert decision.habilidad.descripcion == ""
    assert decision.evidencia == [logro]


def test_no_normaliza_nominalizacion_de_frase_no_incluida(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    nombre = "Evaluación comparativa de acciones ATL y BTL"
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            nombre,
            habilidad=analista_llm.ConceptoPropuesto(nombre=nombre),
        ),
    )
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(nombre),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert not resultado.propuestas
    reporte = next(
        fila for fila in resultado.reportes if fila.get("estado") == "REVISAR_VALIDACION"
    )
    habilidad = reporte.get("habilidad")
    assert isinstance(habilidad, dict)
    assert habilidad["nombre"] == nombre
    assert reporte["problemas"] == ["HABILIDAD_SIN_VERBO_OBSERVABLE"]


@pytest.mark.parametrize(
    "verbo",
    [
        "Criticar",
        "Ejemplificar",
        "Defender",
        "Realizar",
        "Configurar",
        "Integrar",
        "Describir",
        "Clasificar",
        "Redactar",
        "Categorizar",
    ],
)
def test_allowlist_admite_verbos_profesionales_observados(verbo: str) -> None:
    logro = f"{verbo} evidencias curriculares de marketing"
    decision = _decision_para(logro, habilidad=analista_llm.ConceptoPropuesto(nombre=logro))
    caso = {
        "logro": logro,
        "herramientas_detectadas": [],
        "evidencia_herramientas": [],
    }

    assert "HABILIDAD_SIN_VERBO_OBSERVABLE" not in analista_llm._validar_decision(decision, caso)


def test_allowlist_mantiene_comprender_como_no_observable() -> None:
    logro = "Comprender evidencias curriculares de marketing"
    decision = _decision_para(logro, habilidad=analista_llm.ConceptoPropuesto(nombre=logro))

    assert "HABILIDAD_SIN_VERBO_OBSERVABLE" in analista_llm._validar_decision(
        decision,
        {"logro": logro, "herramientas_detectadas": [], "evidencia_herramientas": []},
    )


def test_grounding_no_reduce_aplicar_crm_a_su_verbo() -> None:
    logro = "Aplicar CRM"
    decision = _decision_para(
        logro,
        habilidad=analista_llm.ConceptoPropuesto(nombre=logro),
        evidencia=["Aplicar"],
    )
    caso = {
        "curso": "Herramientas de gestión",
        "sumilla": logro,
        "logro_general": logro,
        "logro": logro,
        "competencias_declaradas": [],
        "herramientas_detectadas": [],
        "evidencia_herramientas": [],
    }

    errores = analista_llm._validar_decision(decision, caso)

    assert "HABILIDAD_SIN_ANCLA_EVIDENCIA" in errores


@pytest.mark.parametrize("declarada", [False, True])
def test_competencia_debe_anclarse_en_fuente_o_declararse(declarada: bool) -> None:
    logro = "Analizar datos de mercado para identificar segmentos"
    competencia = "Gestionar nóminas de personal"
    decision = _decision_para(
        logro,
        competencia=analista_llm.ConceptoPropuesto(nombre=competencia),
        habilidad=analista_llm.ConceptoPropuesto(nombre="Analizar datos de mercado"),
        evidencia=[logro],
    )
    caso = {
        "curso": "Investigación de mercados",
        "sumilla": logro,
        "logro_general": logro,
        "logro": logro,
        "competencias_declaradas": [competencia] if declarada else [],
        "herramientas_detectadas": [],
        "evidencia_herramientas": [],
    }

    errores = analista_llm._validar_decision(decision, caso)

    assert ("COMPETENCIA_SIN_ANCLA_FUENTE" in errores) is not declarada


@pytest.mark.parametrize(
    "competencia",
    [
        "Trabajo en equipo",
        "Comunicación efectiva",
        "Comunicación eficaz",
        "Pensamiento crítico",
        "Aprendizaje autónomo",
        "Ética profesional",
    ],
)
def test_competencias_genericas_se_rechazan_deterministicamente(competencia: str) -> None:
    logro = f"Analizar evidencia con {competencia}"
    decision = _decision_para(
        logro,
        competencia=analista_llm.ConceptoPropuesto(nombre=competencia),
        habilidad=analista_llm.ConceptoPropuesto(nombre="Analizar evidencia curricular"),
        evidencia=[logro],
    )
    caso = {
        "curso": "Investigación aplicada",
        "sumilla": logro,
        "logro_general": logro,
        "logro": logro,
        "competencias_declaradas": [competencia],
        "herramientas_detectadas": [],
        "evidencia_herramientas": [],
    }

    assert "COMPETENCIA_GENERICA" in analista_llm._validar_decision(decision, caso)


def test_normalizacion_especifica_vive_en_el_perfil_de_la_carrera(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    logro = "Estimación y predicción multivariante"
    decision = _decision_para(
        logro,
        competencia=analista_llm.ConceptoPropuesto(nombre="Predicción multivariante"),
    )
    analista = _LLMDecisionesFalso("gpt-test", decision)
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)
    monkeypatch.setattr(
        analista_llm,
        "_cargar_perfil",
        lambda _carrera, _periodo: {
            "carrera": "FINANZAS",
            "periodo": "2026-1",
            "normalizaciones_habilidad": {logro: "Estimar y predecir multivariante financiero"},
        },
    )

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "FINANZAS",
        "2026-1",
        tmp_path,
    )

    assert next(iter(resultado.propuestas.values())).habilidad.nombre == (
        "Estimar y predecir multivariante financiero"
    )


def test_logro_sin_programa_analitico_no_respalda_una_herramienta() -> None:
    logro = (
        "Desarrollar el Tablero de comando (Balanced Scorecard) para hacer seguimiento "
        "y control de la gestión."
    )
    caso = next(analista_llm._casos_curriculares(_registros_para(logro), _catalogo_vacio(), {}))
    decision = _decision_para(
        logro,
        herramientas=[
            analista_llm.HerramientaPropuesta(
                nombre="Balanced Scorecard",
                evidencia="Balanced Scorecard",
            )
        ],
    )

    assert caso["herramientas_detectadas"] == []
    candidatas = caso["evidencia_herramientas_candidata"]
    assert isinstance(candidatas, list)
    assert {item["seccion"] for item in candidatas if isinstance(item, dict)} >= {
        "Logro de aprendizaje"
    }
    assert "HERRAMIENTA_NO_DETECTADA:Balanced Scorecard" in analista_llm._validar_decision(
        decision, caso
    )


@pytest.mark.parametrize("nombre", ["Balanced Scorecard", "CRM"])
def test_rechaza_evidencia_contextual_sin_nombre_de_herramienta(nombre: str) -> None:
    logro = "Desarrollar seguimiento y control de la gestión."
    caso = next(analista_llm._casos_curriculares(_registros_para(logro), _catalogo_vacio(), {}))
    decision = _decision_para(
        logro,
        herramientas=[
            analista_llm.HerramientaPropuesta(
                nombre=nombre,
                evidencia="seguimiento y control de la gestión",
            )
        ],
    )

    assert f"HERRAMIENTA_NO_DETECTADA:{nombre}" in analista_llm._validar_decision(decision, caso)
    assert (
        salida._herramientas_llm_nuevas(
            decision,
            {
                "herramientas_evidencia": [
                    {
                        "seccion": "Programa analítico",
                        "texto": "Seguimiento y control de la gestión.",
                    }
                ]
            },
            (),
        )
        == ()
    )


def test_confianza_del_analista_se_conserva_sin_rutear_otra_llamada(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Aplicar investigación de mercados y CRM en cadenas retail."
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            herramientas=[analista_llm.HerramientaPropuesta(nombre="CRM", evidencia="CRM")],
            confianza=0.89,
        ),
    )
    roles: list[str] = []

    def obtener(rol: str, **_kwargs: object):
        roles.append(rol)
        return analista

    monkeypatch.setattr(
        analista_llm,
        "obtener_llm",
        obtener,
    )

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro, programa_analitico=["CRM"]),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert resultado.propuestas
    assert roles == ["analista_curricular"]
    assert any(
        fila["estado"] == "PENDIENTE_REVISION_HUMANA" and fila["confianza"] == 0.89
        for fila in resultado.reportes
    )
    caso = next(analista_llm._casos_curriculares(_registros_para(logro), _catalogo_vacio(), {}))
    assert caso["herramientas_detectadas"] == []


def test_herramienta_nueva_requiere_evidencia_de_programa_analitico() -> None:
    decision = analista_llm.DecisionCurricular(
        id_habilidad_fuente="HAB_SRC_nueva",
        competencia=analista_llm.ConceptoPropuesto(nombre="Analítica de marketing"),
        habilidad=analista_llm.ConceptoPropuesto(nombre="Analizar audiencias de campaña"),
        herramientas=[
            analista_llm.HerramientaPropuesta(
                nombre="Google Analytics",
                evidencia="Google Analytics",
            )
        ],
        evidencia=["Analizar audiencias de campaña"],
        confianza=0.9,
    )

    nuevas = salida._herramientas_llm_nuevas(
        decision,
        {"programa_analitico": ["Google Analytics"]},
        (),
    )

    assert len(nuevas) == 1
    assert nuevas[0][0].nombre == "Google Analytics"


def test_no_publica_herramienta_literal_fuera_del_programa_analitico() -> None:
    logro = "Aplicar Balanced Scorecard para el seguimiento de la gestión."
    decision = _decision_para(
        logro,
        herramientas=[
            analista_llm.HerramientaPropuesta(
                nombre="Balanced Scorecard",
                evidencia="Balanced Scorecard",
            )
        ],
    )

    nuevas = salida._herramientas_llm_nuevas(decision, {"logro_actual": logro}, ())

    assert nuevas == ()


def test_no_publica_herramienta_solo_por_contexto_generico_del_logro() -> None:
    logro = "Aplicar seguimiento y control de la gestión."
    decision = _decision_para(
        logro,
        herramientas=[analista_llm.HerramientaPropuesta(nombre="CRM", evidencia="seguimiento")],
    )

    assert salida._herramientas_llm_nuevas(decision, {"logro_actual": logro}, ()) == ()


def test_normaliza_tipo_de_competencia_llm_al_contrato_csv() -> None:
    dura = salida._concepto_decidido(
        _catalogo_vacio(),
        "Gestión de campañas de marketing",
        "Planificación y gestión de campañas.",
        "competencia profesional de Marketing",
        "COMP",
    )
    blanda = salida._concepto_decidido(
        _catalogo_vacio(),
        "Comunicación efectiva",
        "Comunicar con claridad.",
        "competencia blanda",
        "COMP",
    )

    assert dura.tipo == "dura"
    assert blanda.tipo == "blanda"


def test_alias_ms_word_se_consolida_con_microsoft_word_detectado() -> None:
    decision = _decision_para(
        "Elaborar documentos profesionales.",
        herramientas=[analista_llm.HerramientaPropuesta(nombre="MS Word", evidencia="MS Word")],
    )
    microsoft_word = ConceptoCHH("WORD", "Microsoft Word", "Procesador de texto", "herramienta")
    detectada = salida.HerramientaDetectada(
        microsoft_word,
        "Software",
        "Microsoft Word",
        "microsoft word",
    )

    nuevas = salida._herramientas_llm_nuevas(
        decision,
        {"herramientas_evidencia": [{"seccion": "Software", "texto": "Microsoft Word"}]},
        (detectada,),
    )

    assert nuevas == ()


def test_los_cinco_encabezados_csv_siguen_siendo_exactos(tmp_path: Path) -> None:
    esperados = {
        "curso.csv": [
            "id_curso",
            "nombre_curso",
            "coordinador",
            "creditos",
            "nivel",
            "tipo_curso",
            "codigo_curso",
            "id_carrera",
        ],
        "catalogo_competencias.csv": [
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve_competencia",
            "tipo_competencia",
            "codigo_competencia",
        ],
        "catalogo_habilidades.csv": [
            "id_habilidad",
            "nombre_habilidad",
            "descripcion_breve",
        ],
        "catalogo_herramientas.csv": [
            "id_herramienta",
            "nombre_herramienta",
            "descripcion_breve_herramienta",
        ],
        "cobertura_curricular.csv": [
            "id_cob_curricular",
            "id_curso",
            "id_silabo",
            "id_competencia",
            "id_habilidad",
            "id_herramienta",
        ],
    }

    for nombre, columnas in salida.ARCHIVOS_SALIDA:
        ruta = tmp_path / nombre
        salida._escribir_csv(ruta, columnas, [])
        with ruta.open(encoding="utf-8-sig", newline="") as archivo:
            assert next(csv.reader(archivo)) == esperados[nombre]


def test_acepta_nps_evidenciado_en_programa_analitico(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Evaluar la satisfacción de clientes"
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            herramientas=[analista_llm.HerramientaPropuesta(nombre="NPS", evidencia="NPS")],
        ),
    )
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(
            logro,
            programa_analitico=[
                "Indicadores de experiencia del cliente: Net Promoter Score (NPS)."
            ],
        ),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(resultado.propuestas) == 1


def test_caso_expone_v_y_vi_y_no_promueve_recursos_genericos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Construir procesos de extracción, transformación y carga"
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(logro),
    )
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)
    registros = _registros_para(
        logro,
        programa_analitico=[
            "Semana 4 | ETL | Lab SQL-SSIS",
            "Semana 7 | Gobierno de datos | Laboratorio ETL - Analysis Services",
        ],
        herramientas_evidencia=[
            {
                "seccion": "Recursos de aprendizaje",
                "texto": "Presentaciones, software, calculadoras y plataformas.",
            }
        ],
    )
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos.update(
        {
            "metodologias_ensenanza": "Clase magistral y ejercicios prácticos.",
            "recursos_aprendizaje": "Presentaciones, software, calculadoras y plataformas.",
            "programa_analitico_detalle": [
                {"semana": "4", "pagina": "2", "texto": "Semana 4 | ETL | Lab SQL-SSIS"},
                {
                    "semana": "7",
                    "pagina": "2",
                    "texto": "Semana 7 | Gobierno de datos | Laboratorio ETL - Analysis Services",
                },
            ],
            "texto_relevante": (
                "Construir procesos de extracción, transformación y carga. "
                "Semana 4 ETL Lab SQL-SSIS."
            ),
            "texto_fuente": "Contenido VI. Referencias https://bibliografia.example",
        }
    )

    caso = next(analista_llm._casos_curriculares(registros, _catalogo_vacio(), {}))

    evidencias = caso["evidencia_herramientas"]
    assert isinstance(evidencias, list)
    assert any("SQL-SSIS" in str(item) for item in evidencias)
    assert any("Analysis Services" in str(item) for item in evidencias)
    assert not any("bibliografia.example" in str(item) for item in evidencias)
    assert caso["herramientas_detectadas"] == []

    prompt = analista_llm._prompt_analista((caso,), {}, "SISTEMAS", "2026-1")
    assert "recursos_aprendizaje" not in prompt
    assert "SQL-SSIS" in prompt
    assert "bibliografia.example" not in prompt


def test_programa_analitico_no_convierte_conceptos_curriculares_en_software() -> None:
    logro = "Construir procesos de extracción, transformación y carga"
    registros = _registros_para(
        logro,
        programa_analitico=[
            "Semana 4 | ETL | Lab SQL-SSIS",
            "Semana 10 | Procesos de Negocio | Laboratorio Power BI - Conexión a SQL",
            "Semana 11 | Visualización | Laboratorio Power BI - Conexión a Cubo y BSC",
            "Semana 12 | Cultura de medición | KPIs en Power BI",
            "Semana 13 | Tendencias | Modelos predictivos en Excel, Orange y Python",
        ],
    )
    catalogo = _catalogo_con_herramientas(
        "ETL",
        "SQL",
        "Cubo",
        "KPI",
        "BSC",
        "SQL-SSIS",
        "Power BI",
        "Excel",
        "Orange",
        "Python",
    )

    caso = next(analista_llm._casos_curriculares(registros, catalogo, {}))

    assert caso["herramientas_detectadas"] == [
        "Excel",
        "Orange",
        "Power BI",
        "Python",
        "SQL-SSIS",
    ]


def test_payload_semantico_agrupa_silabo_y_oculta_linaje_interno() -> None:
    logro_1 = "Contrastar señales operativas para priorizar mejoras."
    logro_2 = "Diseñar tableros trazables para comunicar hallazgos."
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos.update(
        {
            "curso": "Laboratorio de decisiones",
            "sumilla": "Integra evidencia operativa en decisiones reproducibles.",
            "logro_general": "Sustenta decisiones con datos verificables.",
            "logros_especificos": [
                {"orden": "7", "descripcion": logro_1},
                {"orden": "8", "descripcion": logro_2},
            ],
            "competencias_declaradas": [
                {
                    "codigo": "ZX9",
                    "nombre": "Razonamiento aplicado",
                    "descripcion": "Evalúa evidencia para decisiones justificadas.",
                }
            ],
            "programa_analitico_detalle": [
                {
                    "semana": "2",
                    "pagina": "5",
                    "evaluacion": "3",
                    "tema": "Matrices",
                    "contenido": "Análisis con QGIS y registros",
                    "texto": "Semana 2 | Matrices | Análisis con QGIS y registros 3",
                },
                {
                    "semana": "3",
                    "pagina": "5",
                    "evaluacion": "4",
                    "tema": "Tableros",
                    "contenido": "Visualización con Metabase",
                    "texto": "Semana 3 | Tableros | Visualización con Metabase 4",
                },
            ],
        }
    )
    casos = tuple(analista_llm._casos_curriculares(registros, _catalogo_vacio(), {}))

    prompt = analista_llm._prompt_analista(casos, {"hash": "no-viaja"}, "PRUEBA", "2031-2")
    payload = json.loads(prompt.split("CASOS:\n", maxsplit=1)[1])
    serializado = json.dumps(payload, ensure_ascii=False)

    assert len(payload) == 1
    assert payload[0]["logros_especificos"] == [logro_1, logro_2]
    assert payload[0]["temas_programa"] == [
        "Matrices | Análisis con QGIS y registros",
        "Tableros | Visualización con Metabase",
    ]
    assert serializado.count("Laboratorio de decisiones") == 1
    assert all(referencia not in serializado for referencia in ("ZX9", "L7", "L8"))
    for clave_prohibida in (
        "referencia",
        "id_habilidad_fuente",
        "id_silabo",
        "id_curso",
        "codigo_curso",
        "archivo",
        "texto_fuente",
        "texto_relevante",
        "contexto_recuperado",
        "fuentes",
        "codigo",
        "semana",
        "evaluacion",
        "hash",
    ):
        assert f'"{clave_prohibida}"' not in serializado

    respuesta = analista_llm.LoteDecisionesCurricularesLLM(
        decisiones=[
            analista_llm.DecisionCurricularLLM(
                logro=logro_1,
                competencia=analista_llm.ConceptoPropuesto(nombre="Razonamiento aplicado"),
                habilidad=analista_llm.ConceptoPropuesto(nombre=logro_1),
                evidencia=[logro_1],
                confianza=0.9,
            ),
            analista_llm.DecisionCurricularLLM(
                logro=logro_2,
                competencia=analista_llm.ConceptoPropuesto(nombre="Comunicación analítica"),
                habilidad=analista_llm.ConceptoPropuesto(nombre=logro_2),
                evidencia=[logro_2],
                confianza=0.9,
            ),
        ]
    )
    decisiones = analista_llm._asignar_decisiones_por_orden(casos, respuesta)
    assert [decision.id_habilidad_fuente for decision in decisiones.decisiones] == [
        caso["id_habilidad_fuente"] for caso in casos
    ]


def test_payload_semantico_preserves_every_program_week() -> None:
    weeks = [
        {
            "semana": str(number),
            "tema": f"Topic {number}",
            "contenido": f"Content {number}",
        }
        for number in range(1, 17)
    ]
    payload = analista_llm._payload_semantico_lote(
        (
            {
                "id_silabo": "SIL_1",
                "curso": "Complete program",
                "competencias_declaradas": [],
                "programa_analitico_detalle": weeks,
            },
        )
    )

    assert payload[0]["temas_programa"] == [
        f"Topic {number} | Content {number}" for number in range(1, 17)
    ]


def test_payload_semantico_falls_back_to_program_when_detail_is_empty() -> None:
    payload = analista_llm._payload_semantico_lote(
        (
            {
                "id_silabo": "SIL_1",
                "curso": "DOCX program",
                "competencias_declaradas": [],
                "programa_analitico_detalle": [],
                "programa_analitico": [
                    "Topic 1 | Content 1",
                    "Topic 2 | Content 2",
                ],
            },
        )
    )

    assert payload[0]["temas_programa"] == [
        "Topic 1 | Content 1",
        "Topic 2 | Content 2",
    ]


def test_mapeo_posicional_rechaza_omision_del_primer_logro() -> None:
    """Una respuesta corta no puede asociar el segundo logro al primer ID interno."""

    primer_logro = "Diagnosticar una situación con evidencia verificable."
    segundo_logro = "Diseñar una respuesta profesional trazable."
    registros = _registros_para(primer_logro)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"].append({"orden": "2", "descripcion": segundo_logro})
    casos = tuple(analista_llm._casos_curriculares(registros, _catalogo_vacio(), {}))
    respuesta = analista_llm.LoteDecisionesCurricularesLLM.model_validate(
        {
            "decisiones": [
                {
                    "logro_fuente": segundo_logro,
                    "competencia": {"nombre": "Diseño profesional"},
                    "habilidad": {"nombre": segundo_logro},
                    "evidencia": [segundo_logro],
                    "confianza": 0.9,
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="cardinalidad"):
        analista_llm._asignar_decisiones_por_orden(casos, respuesta)


def test_mapeo_posicional_rechaza_respuesta_reordenada() -> None:
    primer_logro = "Diagnosticar una situación con evidencia verificable."
    segundo_logro = "Diseñar una respuesta profesional trazable."
    registros = _registros_para(primer_logro)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"].append({"orden": "2", "descripcion": segundo_logro})
    casos = tuple(analista_llm._casos_curriculares(registros, _catalogo_vacio(), {}))
    respuesta = analista_llm.LoteDecisionesCurricularesLLM.model_validate(
        {
            "decisiones": [
                {
                    "logro_fuente": segundo_logro,
                    "competencia": {"nombre": "Diseño profesional"},
                    "habilidad": {"nombre": segundo_logro},
                    "confianza": 0.9,
                },
                {
                    "logro_fuente": primer_logro,
                    "competencia": {"nombre": "Diagnóstico profesional"},
                    "habilidad": {"nombre": primer_logro},
                    "confianza": 0.9,
                },
            ]
        }
    )

    with pytest.raises(ValueError, match="orden"):
        analista_llm._asignar_decisiones_por_orden(casos, respuesta)


def test_un_silabo_con_mas_de_veinte_logros_permanece_en_un_solo_lote() -> None:
    casos = tuple(
        {
            "id_silabo": "SIL_UNICO",
            "id_habilidad_fuente": f"HAB_SRC_{indice}",
            "logro": f"Analizar evidencia curricular {indice}.",
        }
        for indice in range(21)
    )

    lotes = tuple(analista_llm._trocear_por_silabo(casos, tamanio=8))
    respuesta = analista_llm.LoteDecisionesCurricularesLLM.model_validate(
        {
            "decisiones": [
                {
                    "logro_fuente": caso["logro"],
                    "competencia": {"nombre": "Análisis curricular"},
                    "habilidad": {"nombre": caso["logro"]},
                    "confianza": 0.9,
                }
                for caso in casos
            ]
        }
    )

    assert lotes == (casos,)
    assert len(respuesta.decisiones) == len(casos)


@pytest.mark.parametrize("alias", ["MS Word", "MS-word"])
def test_acepta_alias_grafico_de_microsoft_word(
    alias: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Elaborar documentos profesionales"
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            herramientas=[analista_llm.HerramientaPropuesta(nombre=alias, evidencia=alias)],
        ),
    )
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(
            logro,
            herramientas_evidencia=[{"seccion": "Software", "texto": "Microsoft Word"}],
        ),
        _catalogo_con_herramientas("Microsoft Word"),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(resultado.propuestas) == 1


def test_rechaza_herramienta_sin_evidencia_estructurada(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Evaluar la satisfacción de clientes"
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            herramientas=[analista_llm.HerramientaPropuesta(nombre="NPS", evidencia="NPS")],
        ),
    )
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)
    registros = _registros_para(logro)
    datos = registros[0].get("datos")
    assert isinstance(datos, dict)
    datos["texto_relevante"] = "Indicador NPS de satisfacción."

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert not resultado.propuestas
    assert any(
        "HERRAMIENTA_NO_DETECTADA:NPS" in problemas
        for fila in resultado.reportes
        if isinstance(problemas := fila.get("problemas"), list)
    )


def test_analista_unico_no_instancia_modelo_residual(monkeypatch, tmp_path: Path) -> None:
    logro = "Evaluar campañas de marketing"
    luna = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(logro, requiere_revision=True),
    )
    roles: list[str] = []

    def obtener(rol: str, **_kwargs: object):
        roles.append(rol)
        return luna

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "false")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(resultado.propuestas) == 1
    assert resultado.decisiones_escaladas == 0
    assert "analista_curricular_residual" not in roles


def test_revision_solicitada_por_analista_queda_pendiente_sin_segunda_llamada(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logro = "Evaluar campañas de marketing"
    luna_analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(logro, requiere_revision=True),
    )
    roles: list[str] = []

    def obtener(rol: str, **_kwargs: object):
        roles.append(rol)
        return luna_analista

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "true")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(resultado.propuestas) == 1
    assert resultado.modelo_analista_residual == "no_ejecutado"
    assert resultado.decisiones_escaladas == 0
    assert roles == ["analista_curricular"]


def test_analista_no_reintenta_error_de_herramienta(monkeypatch, tmp_path: Path) -> None:
    logro = "Evaluar campañas de marketing"
    luna = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            herramientas=[
                analista_llm.HerramientaPropuesta(
                    nombre="Herramienta inventada",
                    evidencia="Herramienta inventada",
                )
            ],
        ),
    )
    roles: list[str] = []

    def obtener(rol: str, **_kwargs: object):
        roles.append(rol)
        return luna

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "true")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert not resultado.propuestas
    assert resultado.decisiones_escaladas == 0
    assert "analista_curricular_residual" not in roles


def test_reintento_restituye_decision_omitida_por_luna(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Evaluar campañas de marketing"
    luna = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[], [_decision_para(logro)]],
    )
    roles: list[str] = []

    def obtener(rol: str, **_kwargs: object):
        roles.append(rol)
        return luna

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "true")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    id_habilidad = analista_llm._hash_id("HAB_SRC", "SIL_1", "1", logro)
    assert id_habilidad in resultado.propuestas
    assert resultado.decisiones_escaladas == 0
    assert luna.logros_por_llamada == [[logro], [logro]]
    assert "analista_curricular_residual" not in roles
    assert {
        fila["id_habilidad_fuente"] for fila in resultado.reportes if "id_habilidad_fuente" in fila
    } == {id_habilidad}


def test_reintenta_una_vez_solo_los_ids_omitidos_y_deja_traza(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro_1 = "Evaluar campañas de marketing"
    logro_2 = "Analizar resultados de campañas"
    decision_1 = _decision_para_orden(logro_1, "1")
    decision_2 = _decision_para_orden(logro_2, "2")
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[decision_1], [decision_2]],
    )
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"orden": "1", "descripcion": logro_1},
        {"orden": "2", "descripcion": logro_2},
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    id_1 = decision_1.id_habilidad_fuente
    id_2 = decision_2.id_habilidad_fuente
    assert set(resultado.propuestas) == {id_1, id_2}
    assert analista.logros_por_llamada == [[logro_1, logro_2], [logro_2]]
    traza = next(fila for fila in resultado.reportes if fila["tipo"] == "analista_reintento")
    assert traza["ids_habilidad_fuente"] == [id_2]
    assert traza["ids_recuperados"] == [id_2]
    assert traza["ids_sin_decision"] == []


def test_reintento_omitido_no_duplica_decisiones_y_conserva_sin_decision_llm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro_1 = "Evaluar campañas de marketing"
    logro_2 = "Analizar resultados de campañas"
    decision_1 = _decision_para_orden(logro_1, "1")
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[decision_1], []],
    )
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"orden": "1", "descripcion": logro_1},
        {"orden": "2", "descripcion": logro_2},
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    id_1 = decision_1.id_habilidad_fuente
    id_2 = analista_llm._hash_id("HAB_SRC", "SIL_1", "2", logro_2)
    assert set(resultado.propuestas) == {id_1}
    assert analista.logros_por_llamada == [[logro_1, logro_2], [logro_2]]
    assert [
        fila
        for fila in resultado.reportes
        if fila.get("id_habilidad_fuente") == id_1 and fila["estado"] == "PENDIENTE_REVISION_HUMANA"
    ]
    reporte_omitido = next(
        fila for fila in resultado.reportes if fila.get("id_habilidad_fuente") == id_2
    )
    assert reporte_omitido["problemas"] == ["SIN_DECISION_LLM"]


def test_decision_omitida_por_luna_queda_reportada_sin_escalamiento(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Evaluar campañas de marketing"
    luna = _LLMLoteDecisionesFalso("gpt-5.6-luna-test", [])
    roles: list[str] = []

    def obtener(rol: str, **_kwargs: object):
        roles.append(rol)
        return luna

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "false")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    id_habilidad = analista_llm._hash_id("HAB_SRC", "SIL_1", "1", logro)
    assert not resultado.propuestas
    assert resultado.decisiones_escaladas == 0
    reporte = next(
        fila for fila in resultado.reportes if fila.get("id_habilidad_fuente") == id_habilidad
    )
    assert {clave: valor for clave, valor in reporte.items() if clave != "contexto_auditoria"} == {
        "tipo": "decision_curricular",
        "estado": "REVISAR_SIN_DECISION_LLM",
        "id_habilidad_fuente": id_habilidad,
        "problemas": ["SIN_DECISION_LLM"],
    }
    assert reporte["contexto_auditoria"] == resultado.auditoria_contexto
    assert "analista_curricular_residual" not in roles


def test_prompts_reciben_contexto_recuperado_y_auditoria(monkeypatch, tmp_path: Path) -> None:
    logro = "Analizar campañas de marketing"
    catalogo = CatalogoCHH(
        competencias=(ConceptoCHH("COMP_1", "Gestión de campañas", "marketing"),),
        habilidades=(ConceptoCHH("HAB_1", "Analizar campañas", "marketing"),),
        herramientas=(),
        ejemplos_por_habilidad={},
        origen=("test",),
        version="catalogo-prueba",
    )
    analista = _LLMDecisionesFalso("gpt-5.6-luna-test", _decision_para(logro))
    prompts: list[str] = []
    original_invoke = analista.invoke

    def capturar(prompt: str):
        prompts.append(prompt)
        return original_invoke(prompt)

    monkeypatch.setattr(analista, "invoke", capturar)
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)
    monkeypatch.setattr(
        analista_llm,
        "_cargar_perfil",
        lambda _carrera, _periodo: {
            "carrera": "MARKETING",
            "periodo": "2026-1",
            "estado": "BORRADOR",
            "revision": "prueba-r1",
            "dominios": ["Dominio defensivo"],
            "reglas": ["Regla defensiva"],
            "exclusiones": ["Exclusión defensiva"],
            "contraejemplos": ["Contraejemplo defensivo"],
            "competencias_preferidas": ["Competencia no aprobada"],
            "aliases": {"no enviar": "Alias no aprobado"},
        },
    )

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        catalogo,
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(prompts) == 1
    assert "contexto_recuperado" not in prompts[0]
    assert "Gestión de campañas" not in prompts[0]
    assert "Alias no aprobado" not in prompts[0]
    assert "Competencia no aprobada" not in prompts[0]
    assert "Dominio defensivo" in prompts[0]
    assert "Regla defensiva" in prompts[0]
    assert "Exclusión defensiva" in prompts[0]
    assert "Contraejemplo defensivo" in prompts[0]
    caso = next(
        analista_llm._casos_curriculares(_registros_para(logro), catalogo, {"estado": "BORRADOR"})
    )
    contexto = caso["contexto_recuperado"]
    assert isinstance(contexto, dict)
    perfil_referencia = contexto["perfil_referencia"]
    assert perfil_referencia.keys() == {"estado", "revision", "hash"}
    assert resultado.auditoria_contexto is not None
    assert resultado.auditoria_contexto["version_catalogo"] == "catalogo-prueba"
    assert all("contexto_auditoria" in fila for fila in resultado.reportes)


def test_progreso_llm_cuenta_cache_y_silabos_unicos_sin_duplicar_reintentos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro_1 = "Evaluar campañas de marketing"
    logro_2 = "Analizar resultados de campañas"
    decision_1 = _decision_para_orden(logro_1, "1")
    decision_2 = _decision_para_orden(logro_2, "2")
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[decision_1, decision_2]],
    )
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"orden": "1", "descripcion": logro_1},
        {"orden": "2", "descripcion": logro_2},
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    progresos_primera = []
    analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        al_actualizar_progreso=progresos_primera.append,
    )
    assert progresos_primera[-1].decisiones_cacheadas == 2

    progresos = []
    analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        al_actualizar_progreso=progresos.append,
    )

    assert analista.logros_por_llamada == [[logro_1, logro_2]]
    progreso_chunk = next(
        progreso
        for progreso in progresos
        if progreso.fase == "analista" and progreso.chunks_completados == 1
    )
    assert progreso_chunk.chunks_totales == 1
    assert progreso_chunk.logros_procesados == 2
    assert progreso_chunk.silabos_procesados == 1
    assert progreso_chunk.decisiones_cacheadas == 2
    assert progreso_chunk.reintentos == 0
    assert progreso_chunk.ultimo_chunk is not None
    assert progreso_chunk.ultimo_chunk.logros == 2
    assert progreso_chunk.ultimo_chunk.silabos == 1
    assert progreso_chunk.eventos[-1].mensaje.startswith("Chunk 1/1 de Analista LLM completado")
    assert progreso_chunk.eventos[-1].decisiones_cacheadas == 2
    assert [evento.secuencia for evento in progreso_chunk.eventos] == list(
        range(1, len(progreso_chunk.eventos) + 1)
    )
    assert progresos[-1].fase == "finalizando"


def test_progreso_llm_conserva_historial_y_separa_silabos_detectados(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    descripciones = [f"Evaluar campaña de marketing {indice}" for indice in range(1, 10)]
    decisiones = [
        _decision_para_orden(descripcion, str(indice))
        for indice, descripcion in enumerate(descripciones, start=1)
    ]
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [decisiones],
    )
    registros = _registros_para(descripciones[0])
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"orden": str(indice), "descripcion": descripcion}
        for indice, descripcion in enumerate(descripciones, start=1)
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)
    progreso_inicial = ProgresoLimpiezaLLM(
        fase="extrayendo",
        chunks_completados=0,
        chunks_totales=0,
        logros_procesados=0,
        logros_totales=9,
        silabos_procesados=0,
        silabos_totales=76,
        decisiones_cacheadas=0,
        reintentos=0,
        silabos_detectados=76,
    ).con_evento("Logros detectados: 9. Sílabos detectados: 76/76.")
    progresos = []

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        al_actualizar_progreso=progresos.append,
        progreso_inicial=progreso_inicial,
    )

    progreso_chunk_1 = next(
        progreso
        for progreso in progresos
        if progreso.fase == "analista" and progreso.chunks_completados == 1
    )
    assert progreso_chunk_1.silabos_detectados == 76
    assert progreso_chunk_1.silabos_procesados == 1
    assert progreso_chunk_1.chunks_totales == 1
    assert progreso_chunk_1.logros_procesados == 9
    mensajes_chunk_1 = [evento.mensaje for evento in progreso_chunk_1.eventos]
    assert any("Chunk 1/1" in mensaje for mensaje in mensajes_chunk_1)
    assert mensajes_chunk_1[0] == "Logros detectados: 9. Sílabos detectados: 76/76."
    assert resultado.progreso is not None
    assert len(resultado.progreso.eventos) >= len(progreso_chunk_1.eventos)
    assert resultado.progreso.eventos[-1].secuencia > progreso_chunk_1.eventos[-1].secuencia


def test_historial_de_progreso_se_limita_a_los_ultimos_cien_eventos() -> None:
    progreso = ProgresoLimpiezaLLM(
        fase="analista",
        chunks_completados=0,
        chunks_totales=105,
        logros_procesados=0,
        logros_totales=105,
        silabos_procesados=0,
        silabos_totales=1,
        decisiones_cacheadas=0,
        reintentos=0,
    )

    for indice in range(105):
        progreso = progreso.con_evento(f"Hito {indice + 1}")

    assert len(progreso.eventos) == 100
    assert progreso.eventos[0].secuencia == 6
    assert len(progreso.a_dict()["eventos"]) == 100


def test_cache_jsonl_hit_preserva_lineage_del_caso(monkeypatch, tmp_path: Path) -> None:
    logro = "Analizar campañas de marketing"
    analista = _LLMLoteSecuencialFalso("gpt-5.6-luna-test", [[_decision_para(logro)]])
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol, **_kwargs: analista)

    primero = analista_llm.analizar_registros_curriculares(
        _registros_para(logro), _catalogo_vacio(), "Marketing", "2026-1", tmp_path
    )
    cache = tmp_path / "salidas" / "reportes" / "decisiones_llm_cache.jsonl"
    filas = [json.loads(linea) for linea in cache.read_text(encoding="utf-8").splitlines()]
    segundo = analista_llm.analizar_registros_curriculares(
        _registros_para(logro), _catalogo_vacio(), "Marketing", "2026-1", tmp_path
    )

    esperado = analista_llm._hash_id("HAB_SRC", "SIL_1", "1", logro)
    assert len(filas) == 1
    assert filas[0]["clave_lote"]
    assert list(primero.propuestas) == [esperado]
    assert list(segundo.propuestas) == [esperado]
    assert cache.read_bytes() == b"".join(
        json.dumps(fila, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for fila in sorted(filas, key=lambda fila: fila["clave_lote"])
    )
    assert primero.modelo_analista == segundo.modelo_analista == "gpt-5.6-luna-test"
    assert analista.logros_por_llamada == [[logro]]
