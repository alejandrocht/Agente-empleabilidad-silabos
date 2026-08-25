"""Pruebas del contrato LLM curricular sin llamadas de red."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from threading import Event

import pytest

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH
from agente.normalizador.excepciones import CancelacionSolicitada
from agente.normalizador.modelos import ProgresoLimpiezaLLM
from agente.normalizador.silabos import analista_llm, salida


class _LLMFalso:
    model_name = "gpt-5.6-sol-test"

    def __init__(self) -> None:
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _prompt: str):
        assert self._schema is not None
        if self._schema is analista_llm.LoteDecisionesCurriculares:
            return self._schema(
                decisiones=[
                    analista_llm.DecisionCurricular(
                        id_habilidad_fuente=analista_llm._hash_id(
                            "HAB_SRC", "SIL_1", "L1", "Diseñar campañas de marketing"
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
        return self._schema(
            inspecciones=[
                analista_llm.InspeccionCurricular(
                    id_habilidad_fuente=analista_llm._hash_id(
                        "HAB_SRC", "SIL_1", "L1", "Diseñar campañas de marketing"
                    ),
                    estado="APROBAR",
                    confianza=0.93,
                )
            ]
        )


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
                "logros_especificos": [{"etiqueta": "L1", "descripcion": logro}],
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
        assert self._schema is analista_llm.LoteDecisionesCurriculares
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
        assert self._schema is analista_llm.LoteDecisionesCurriculares
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
        self.ids_por_llamada: list[list[str]] = []

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, prompt: str):
        assert self._schema is analista_llm.LoteDecisionesCurriculares
        casos = json.loads(prompt.split("CASOS:\n", maxsplit=1)[1])
        self.ids_por_llamada.append([caso["id_habilidad_fuente"] for caso in casos])
        return self._schema(decisiones=next(self._respuestas))


class _LLMInspeccionFalso:
    def __init__(self, modelo: str, inspeccion: analista_llm.InspeccionCurricular) -> None:
        self.model_name = modelo
        self._inspeccion = inspeccion
        self._schema = None

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _prompt: str):
        assert self._schema is analista_llm.LoteInspeccionesCurriculares
        return self._schema(inspecciones=[self._inspeccion])


def _decision_para(
    logro: str,
    **cambios: object,
) -> analista_llm.DecisionCurricular:
    decision = analista_llm.DecisionCurricular(
        id_habilidad_fuente=analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro),
        competencia=analista_llm.ConceptoPropuesto(nombre="Gestión de campañas"),
        habilidad=analista_llm.ConceptoPropuesto(nombre=logro),
        evidencia=[logro],
        confianza=0.94,
    )
    return decision.model_copy(update=cambios)


def _decision_para_etiqueta(
    logro: str,
    etiqueta: str,
    **cambios: object,
) -> analista_llm.DecisionCurricular:
    decision = _decision_para(logro).model_copy(
        update={"id_habilidad_fuente": analista_llm._hash_id("HAB_SRC", "SIL_1", etiqueta, logro)}
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


def test_analista_e_inspector_aceptan_decision_con_evidencia(monkeypatch, tmp_path: Path) -> None:
    analista = _LLMFalso()
    inspector = _LLMFalso()

    def obtener(rol: str):
        return analista if rol == "analista_curricular" else inspector

    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)
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
                    {"etiqueta": "L1", "descripcion": "Diseñar campañas de marketing"}
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
    assert resultado.modelo_inspector == "gpt-5.6-sol-test"
    assert len(resultado.decisiones) == 1
    assert any(fila["estado"] == "ACEPTADA" for fila in resultado.reportes)


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
                "logros_especificos": [
                    {"etiqueta": "L1", "descripcion": f"Diseñar campaña {indice}"}
                ],
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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: llm)

    with pytest.raises(CancelacionSolicitada):
        analista_llm.analizar_registros_curriculares(
            registros,
            _catalogo_vacio(),
            "Marketing",
            "2026-1",
            tmp_path,
            inspeccionar=False,
            cancelada=cancelada.is_set,
        )

    assert llm.llamadas == 1


def test_normaliza_habilidad_nominalizada_antes_de_validarla(monkeypatch, tmp_path: Path) -> None:
    class LLMNominalizado(_LLMFalso):
        def invoke(self, _prompt: str):
            assert self._schema is not None
            id_habilidad = analista_llm._hash_id(
                "HAB_SRC", "SIL_1", "L1", "Evaluación de campañas de marketing"
            )
            if self._schema is analista_llm.LoteDecisionesCurriculares:
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
                            confianza=0.94,
                        )
                    ]
                )
            return self._schema(
                inspecciones=[
                    analista_llm.InspeccionCurricular(
                        id_habilidad_fuente=id_habilidad,
                        estado="APROBAR",
                        confianza=0.93,
                    )
                ]
            )

    analista = LLMNominalizado()
    inspector = LLMNominalizado()
    monkeypatch.setattr(
        analista_llm,
        "obtener_llm",
        lambda rol: analista if rol == "analista_curricular" else inspector,
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
                    {"etiqueta": "L1", "descripcion": "Evaluación de campañas de marketing"}
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

    decision = next(iter(resultado.decisiones.values()))
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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        inspeccionar=False,
    )

    decision = next(iter(resultado.decisiones.values()))
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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(nombre),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        inspeccionar=False,
    )

    assert not resultado.decisiones
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


def test_logro_respalda_balanced_scorecard_sin_autodetectarlo_como_herramienta() -> None:
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
    assert "HERRAMIENTA_NO_DETECTADA:Balanced Scorecard" not in analista_llm._validar_decision(
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


def test_crm_del_logro_llega_al_inspector_sin_autoclasificarse_como_herramienta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Aplicar investigación de mercados y CRM en cadenas retail."
    analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(
            logro,
            herramientas=[analista_llm.HerramientaPropuesta(nombre="CRM", evidencia="CRM")],
        ),
    )
    inspector = _LLMInspeccionFalso(
        "gpt-5.6-luna-test",
        analista_llm.InspeccionCurricular(
            id_habilidad_fuente=analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro),
            estado="REVISAR",
            confianza=0.8,
            problemas=["CRM requiere revisión curricular."],
        ),
    )
    monkeypatch.setattr(
        analista_llm,
        "obtener_llm",
        lambda rol: analista if rol == "analista_curricular" else inspector,
    )

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert not resultado.decisiones
    assert any(fila["estado"] == "REVISAR_INSPECTOR" for fila in resultado.reportes)
    caso = next(analista_llm._casos_curriculares(_registros_para(logro), _catalogo_vacio(), {}))
    assert caso["herramientas_detectadas"] == []


def test_herramienta_nueva_requiere_evidencia_de_seccion_estructurada() -> None:
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
        {"herramientas_evidencia": [{"seccion": "Software", "texto": "Google Analytics"}]},
        (),
    )

    assert len(nuevas) == 1
    assert nuevas[0][0].nombre == "Google Analytics"


def test_publica_herramienta_literal_en_el_logro_actual() -> None:
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

    assert [herramienta.nombre for herramienta, _ in nuevas] == ["Balanced Scorecard"]
    assert nuevas[0][1] == {"seccion": "Logro de aprendizaje", "texto": logro}


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


def test_los_cuatro_encabezados_csv_siguen_siendo_exactos(tmp_path: Path) -> None:
    esperados = {
        "catalogo_competencias.csv": [
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve_competencia",
            "tipo_competencia",
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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

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
        inspeccionar=False,
    )

    assert len(resultado.decisiones) == 1


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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(
            logro,
            herramientas_evidencia=[{"seccion": "Software", "texto": "Microsoft Word"}],
        ),
        _catalogo_con_herramientas("Microsoft Word"),
        "Marketing",
        "2026-1",
        tmp_path,
        inspeccionar=False,
    )

    assert len(resultado.decisiones) == 1


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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)
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
        inspeccionar=False,
    )

    assert not resultado.decisiones
    assert any(
        "HERRAMIENTA_NO_DETECTADA:NPS" in problemas
        for fila in resultado.reportes
        if isinstance(problemas := fila.get("problemas"), list)
    )


def test_escalamiento_apagado_no_instancia_modelo_residual(monkeypatch, tmp_path: Path) -> None:
    logro = "Evaluar campañas de marketing"
    luna = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(logro, requiere_revision=True),
    )
    roles: list[str] = []

    def obtener(rol: str):
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

    assert not resultado.decisiones
    assert resultado.decisiones_escaladas == 0
    assert "analista_curricular_residual" not in roles
    assert "inspector_curricular_residual" not in roles


def test_escalamiento_activo_acepta_residual_de_terra(monkeypatch, tmp_path: Path) -> None:
    logro = "Evaluar campañas de marketing"
    luna_analista = _LLMDecisionesFalso(
        "gpt-5.6-luna-test",
        _decision_para(logro, requiere_revision=True),
    )
    terra_analista = _LLMDecisionesFalso(
        "gpt-5.6-terra-test",
        _decision_para(logro),
    )
    luna_inspector = _LLMInspeccionFalso(
        "gpt-5.6-luna-test",
        analista_llm.InspeccionCurricular(
            id_habilidad_fuente=analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro),
            estado="APROBAR",
            confianza=0.93,
        ),
    )
    roles: list[str] = []

    def obtener(rol: str):
        roles.append(rol)
        if rol == "analista_curricular":
            return luna_analista
        if rol == "analista_curricular_residual":
            return terra_analista
        return luna_inspector

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "true")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(resultado.decisiones) == 1
    assert resultado.modelo_analista_residual == "gpt-5.6-terra-test"
    assert resultado.decisiones_escaladas == 1
    assert "analista_curricular_residual" in roles


def test_escalamiento_no_reintenta_error_de_herramienta(monkeypatch, tmp_path: Path) -> None:
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

    def obtener(rol: str):
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

    assert not resultado.decisiones
    assert resultado.decisiones_escaladas == 0
    assert "analista_curricular_residual" not in roles


def test_escalamiento_reinspecciona_con_terra_solo_veredicto_revisar(
    monkeypatch, tmp_path: Path
) -> None:
    logro = "Evaluar campañas de marketing"
    luna_analista = _LLMDecisionesFalso("gpt-5.6-luna-test", _decision_para(logro))
    luna_inspector = _LLMInspeccionFalso(
        "gpt-5.6-luna-test",
        analista_llm.InspeccionCurricular(
            id_habilidad_fuente=analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro),
            estado="REVISAR",
            confianza=0.8,
            problemas=["Requiere juicio semántico adicional."],
        ),
    )
    terra_inspector = _LLMInspeccionFalso(
        "gpt-5.6-terra-test",
        analista_llm.InspeccionCurricular(
            id_habilidad_fuente=analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro),
            estado="APROBAR",
            confianza=0.93,
        ),
    )
    roles: list[str] = []

    def obtener(rol: str):
        roles.append(rol)
        if rol == "analista_curricular":
            return luna_analista
        if rol == "inspector_curricular":
            return luna_inspector
        return terra_inspector

    monkeypatch.setenv("NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES", "true")
    monkeypatch.setattr(analista_llm, "obtener_llm", obtener)

    resultado = analista_llm.analizar_registros_curriculares(
        _registros_para(logro),
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
    )

    assert len(resultado.decisiones) == 1
    assert resultado.modelo_inspector_residual == "gpt-5.6-terra-test"
    assert resultado.decisiones_escaladas == 1
    assert "inspector_curricular_residual" in roles


def test_reintento_restituye_decision_omitida_por_luna(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro = "Evaluar campañas de marketing"
    luna = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[], [_decision_para(logro)]],
    )
    roles: list[str] = []

    def obtener(rol: str):
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
        inspeccionar=False,
    )

    id_habilidad = analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro)
    assert id_habilidad in resultado.decisiones
    assert resultado.decisiones_escaladas == 0
    assert luna.ids_por_llamada == [[id_habilidad], [id_habilidad]]
    assert "analista_curricular_residual" not in roles
    assert {
        fila["id_habilidad_fuente"] for fila in resultado.reportes if "id_habilidad_fuente" in fila
    } == {id_habilidad}


def test_reintenta_una_vez_solo_los_ids_omitidos_y_deja_traza(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro_1 = "Evaluar campañas de marketing"
    logro_2 = "Analizar resultados de campañas"
    decision_1 = _decision_para_etiqueta(logro_1, "L1")
    decision_2 = _decision_para_etiqueta(logro_2, "L2")
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[decision_1], [decision_2]],
    )
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"etiqueta": "L1", "descripcion": logro_1},
        {"etiqueta": "L2", "descripcion": logro_2},
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        inspeccionar=False,
    )

    id_1 = decision_1.id_habilidad_fuente
    id_2 = decision_2.id_habilidad_fuente
    assert set(resultado.decisiones) == {id_1, id_2}
    assert analista.ids_por_llamada == [[id_1, id_2], [id_2]]
    traza = next(fila for fila in resultado.reportes if fila["tipo"] == "analista_reintento")
    assert traza["ids_habilidad_fuente"] == [id_2]
    assert traza["ids_recuperados"] == [id_2]
    assert traza["ids_sin_decision"] == []


def test_reintento_omitido_no_duplica_decisiones_y_conserva_sin_decision_llm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro_1 = "Evaluar campañas de marketing"
    logro_2 = "Analizar resultados de campañas"
    decision_1 = _decision_para_etiqueta(logro_1, "L1")
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[decision_1], []],
    )
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"etiqueta": "L1", "descripcion": logro_1},
        {"etiqueta": "L2", "descripcion": logro_2},
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

    resultado = analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        inspeccionar=False,
    )

    id_1 = decision_1.id_habilidad_fuente
    id_2 = analista_llm._hash_id("HAB_SRC", "SIL_1", "L2", logro_2)
    assert set(resultado.decisiones) == {id_1}
    assert analista.ids_por_llamada == [[id_1, id_2], [id_2]]
    assert [
        fila
        for fila in resultado.reportes
        if fila.get("id_habilidad_fuente") == id_1 and fila["estado"] == "ACEPTADA"
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

    def obtener(rol: str):
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
        inspeccionar=False,
    )

    id_habilidad = analista_llm._hash_id("HAB_SRC", "SIL_1", "L1", logro)
    assert not resultado.decisiones
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
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)
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
        inspeccionar=False,
    )

    assert len(prompts) == 1
    assert "contexto_recuperado" in prompts[0]
    assert "Gestión de campañas" in prompts[0]
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
    perfil_prompt = {"estado": "BORRADOR", "revision": "prueba-r1", "hash": "prueba"}
    prompt_inspector = analista_llm._prompt_inspector(
        (caso,), [_decision_para(logro)], perfil_prompt
    )
    assert "contexto_recuperado" in prompt_inspector
    assert "Gestión de campañas" in prompt_inspector
    assert resultado.auditoria_contexto is not None
    assert resultado.auditoria_contexto["version_catalogo"] == "catalogo-prueba"
    assert all("contexto_auditoria" in fila for fila in resultado.reportes)


def test_progreso_llm_cuenta_cache_y_silabos_unicos_sin_duplicar_reintentos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logro_1 = "Evaluar campañas de marketing"
    logro_2 = "Analizar resultados de campañas"
    decision_1 = _decision_para_etiqueta(logro_1, "L1")
    decision_2 = _decision_para_etiqueta(logro_2, "L2")
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [[decision_1, decision_2]],
    )
    registros = _registros_para(logro_1)
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"etiqueta": "L1", "descripcion": logro_1},
        {"etiqueta": "L2", "descripcion": logro_2},
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)

    progresos_primera = []
    analista_llm.analizar_registros_curriculares(
        registros,
        _catalogo_vacio(),
        "Marketing",
        "2026-1",
        tmp_path,
        inspeccionar=False,
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
        inspeccionar=False,
        al_actualizar_progreso=progresos.append,
    )

    assert analista.ids_por_llamada == [
        [decision_1.id_habilidad_fuente, decision_2.id_habilidad_fuente]
    ]
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
        _decision_para_etiqueta(descripcion, f"L{indice}")
        for indice, descripcion in enumerate(descripciones, start=1)
    ]
    analista = _LLMLoteSecuencialFalso(
        "gpt-5.6-luna-test",
        [decisiones[:8], decisiones[8:]],
    )
    registros = _registros_para(descripciones[0])
    datos = registros[0]["datos"]
    assert isinstance(datos, dict)
    datos["logros_especificos"] = [
        {"etiqueta": f"L{indice}", "descripcion": descripcion}
        for indice, descripcion in enumerate(descripciones, start=1)
    ]
    monkeypatch.setattr(analista_llm, "obtener_llm", lambda _rol: analista)
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
        inspeccionar=False,
        al_actualizar_progreso=progresos.append,
        progreso_inicial=progreso_inicial,
    )

    progreso_chunk_1 = next(
        progreso
        for progreso in progresos
        if progreso.fase == "analista" and progreso.chunks_completados == 1
    )
    progreso_chunk_2 = next(
        progreso
        for progreso in progresos
        if progreso.fase == "analista" and progreso.chunks_completados == 2
    )
    mensajes_chunk_2 = [evento.mensaje for evento in progreso_chunk_2.eventos]
    assert progreso_chunk_1.silabos_detectados == 76
    assert progreso_chunk_1.silabos_procesados == 1
    assert len(progreso_chunk_2.eventos) > len(progreso_chunk_1.eventos)
    assert any("Chunk 1/2" in mensaje for mensaje in mensajes_chunk_2)
    assert any("Chunk 2/2" in mensaje for mensaje in mensajes_chunk_2)
    assert mensajes_chunk_2[0] == "Logros detectados: 9. Sílabos detectados: 76/76."
    assert resultado.progreso is not None
    assert len(resultado.progreso.eventos) >= len(progreso_chunk_2.eventos)
    assert resultado.progreso.eventos[-1].secuencia > progreso_chunk_2.eventos[-1].secuencia


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
