from __future__ import annotations

from types import SimpleNamespace

import pytest

from agente.normalizador.silabos.langextract_ciar import (
    PROMPT_EXTRACCION_CIAR,
    DocumentoRazonadoCIAR,
    _nombre_herramienta_generico,
    adaptar_resultado_langextract,
    construir_payload_langextract,
)


def _span(texto: str, cita: str) -> dict[str, int]:
    inicio = texto.index(cita)
    return {"start_pos": inicio, "end_pos": inicio + len(cita)}


def _paquete(texto: str, **atributos: object) -> dict[str, object]:
    evidencia = str(atributos.pop("evidencia_principal", "Analiza datos"))
    herramientas = atributos.pop("herramientas", None)
    if herramientas is None:
        herramientas = [
            {
                "nombre": "Python",
                "tipo_ontologia": "lenguaje",
                "seccion_fuente": "programa_semanal",
                "cita_fuente": {
                    "texto": "Analiza datos con Python",
                    **_span(texto, "Analiza datos con Python"),
                },
                "evidencia_uso": "Analiza datos con Python",
            },
            {
                "nombre": "SQL",
                "tipo_ontologia": "lenguaje",
                "seccion_fuente": "programa_semanal",
                "cita_fuente": {
                    "texto": "Analiza datos con Python y SQL",
                    **_span(texto, "Analiza datos con Python y SQL"),
                },
                "evidencia_uso": "Analiza datos con Python y SQL",
            },
        ]
    return {
        "extraction_class": "paquete_respaldado",
        "extraction_text": evidencia,
        "char_interval": _span(texto, "Analiza datos"),
        "attributes": {
            "habilidad_propuesta": "Analizar datos",
            "competencia_propuesta": "Resolucion de problemas",
            "herramientas": herramientas,
            "contexto_relacion": "La habilidad permite resolver problemas con datos.",
            **atributos,
        },
    }


def test_adapta_paquete_respaldado_con_citas_literales() -> None:
    texto = "Semana 1: Analiza datos con Python y SQL para elaborar reportes."
    bruto = {
        "text": texto,
        "extractions": [
            _paquete(
                texto,
                evidencia_complementaria={
                    "texto": "elaborar reportes",
                    **_span(texto, "elaborar reportes"),
                },
            )
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.pendientes == ()
    assert len(resultado.paquetes_respaldados) == 1
    paquete = resultado.paquetes_respaldados[0]
    assert paquete.habilidad_propuesta == "Analizar datos"
    assert paquete.herramientas == ("Python", "SQL")
    assert paquete.evidencia_principal.texto == "Analiza datos"
    assert paquete.evidencia_complementaria is not None
    assert paquete.evidencia_complementaria.texto == "elaborar reportes"


def test_adapta_objetos_por_duck_typing_sin_importar_el_sdk() -> None:
    texto = "Semana 1: Analiza datos con Python."
    bruto = SimpleNamespace(
        text=texto,
        extractions=[
            SimpleNamespace(
                extraction_class="paquete_respaldado",
                extraction_text="Analiza datos",
                char_interval=SimpleNamespace(**_span(texto, "Analiza datos")),
                attributes={"habilidad_propuesta": "Analizar datos"},
            )
        ],
    )

    resultado = adaptar_resultado_langextract(bruto)

    assert len(resultado.paquetes_respaldados) == 1
    assert resultado.pendientes == ()


def test_herramienta_sin_habilidad_pasa_a_pendiente() -> None:
    texto = "Semana 1: Analiza datos con Python y SQL."
    bruto = {"text": texto, "extractions": [_paquete(texto, habilidad_propuesta="")]}

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.paquetes_respaldados == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "HERRAMIENTA_SIN_HABILIDAD"
    ]


def test_baseline_retains_raw_package_that_strict_rejects() -> None:
    texto = "Semana 1: Gestionar datos con Software."
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": "Gestionar datos",
                "char_interval": _span(texto, "Gestionar datos"),
                "attributes": {
                    "habilidad_propuesta": "Gestion",
                    "competencia_propuesta": "Competencia sin catalogar",
                    "herramientas": [{"nombre": "Software"}],
                },
            }
        ],
    }

    baseline = adaptar_resultado_langextract(bruto, profile="baseline")
    strict = adaptar_resultado_langextract(bruto)

    assert baseline.pendientes == ()
    [paquete] = baseline.paquetes_respaldados
    assert paquete.competencia_propuesta == "Competencia sin catalogar"
    assert paquete.habilidad_propuesta == "Gestion"
    assert paquete.herramientas == ("Software",)
    assert strict.paquetes_respaldados == ()
    assert [pendiente.codigo for pendiente in strict.pendientes] == [
        "HABILIDAD_SIN_ACCION_Y_OBJETO"
    ]


def test_cita_principal_inventada_o_modificada_pasa_a_pendiente() -> None:
    texto = "Semana 1: Analiza datos con Python y SQL."
    bruto = {"text": texto, "extractions": [_paquete(texto, evidencia_principal="Analizo datos")]}

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.paquetes_respaldados == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "CITA_PRINCIPAL_NO_LITERAL"
    ]
    assert resultado.pendientes[0].diagnostico_cita == {
        "texto_modelo": "Analizo datos",
        "intervalo": {"start_pos": 10, "end_pos": 23},
        "fragmento_fuente": "Analiza datos",
        "razon_rechazo": "CITA_PRINCIPAL_NO_LITERAL",
    }


def test_intervalos_invalidos_pasan_a_pendiente() -> None:
    texto = "Semana 1: Analiza datos con Python y SQL."
    bruto = {
        "text": texto,
        "extractions": [
            {
                **_paquete(texto),
                "char_interval": {"start_pos": 20, "end_pos": 5},
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.paquetes_respaldados == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "INTERVALO_CITA_PRINCIPAL_INVALIDO"
    ]


def test_pendientes_del_modelo_se_preservan_separados() -> None:
    texto = "Semana 1: Se utiliza una herramienta no identificada."
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "pendiente",
                "extraction_text": "herramienta no identificada",
                "attributes": {"motivo": "No hay habilidad respaldada para asociarla."},
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.paquetes_respaldados == ()
    assert len(resultado.pendientes) == 1
    assert resultado.pendientes[0].codigo == "PENDIENTE_DECLARADO_POR_MODELO"
    assert resultado.pendientes[0].evidencia_literal == "herramienta no identificada"


def test_payload_razonado_excluye_metadatos_operativos() -> None:
    documento = DocumentoRazonadoCIAR(
        contenido_documental="Semana 1: Analiza datos con Python.",
        ruta="/privado/silabos/curso.pdf",
        hash_fuente="sha256:secreto",
        numero_semana=1,
        metadatos_operativos={"ejecucion": "EJ-123"},
    )

    payload = construir_payload_langextract(documento)

    assert payload == {"text_or_documents": "Semana 1: Analiza datos con Python."}
    assert "ruta" not in payload
    assert "hash_fuente" not in payload
    assert "numero_semana" not in payload
    assert "secreto" not in str(payload)
    assert "evidencia semanal" in PROMPT_EXTRACCION_CIAR.lower()


def test_prompt_prioriza_competencia_de_dominio_sobre_contexto_transversal() -> None:
    prompt = PROMPT_EXTRACCION_CIAR.casefold()

    assert "capacidad profesional o de dominio específica" in prompt
    assert "solo como contexto declarado" in prompt
    assert "no como\n`competencia_propuesta`" in prompt
    assert "acción y objeto" in prompt


def test_adapta_herramienta_nombrada_con_cita_literal() -> None:
    texto = "Semana 1: Ejecutar pruebas de penetración con Metasploit."
    evidencia = "Ejecutar pruebas de penetración con Metasploit"
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Ejecutar pruebas de penetración",
                    "competencia_propuesta": "Ciberseguridad",
                    "herramientas": [
                        {
                            "nombre": "Metasploit",
                            "tipo_ontologia": "software",
                            "seccion_fuente": "programa_semanal",
                            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
                            "evidencia_uso": "Metasploit",
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.pendientes == ()
    assert resultado.paquetes_respaldados[0].herramientas == ("Metasploit",)
    assert resultado.paquetes_respaldados[0].herramientas_propuestas == (
        {
            "nombre": "Metasploit",
            "tipo_ontologia": "software",
            "estado": "PROPUESTA_HITL",
            "requiere_aprobacion_humana": True,
            "seccion_fuente": "programa_semanal",
            "evidencia_literal": evidencia,
            "start_pos": texto.index(evidencia),
            "end_pos": texto.index(evidencia) + len(evidencia),
            "evidencia_uso": "Metasploit",
        },
    )


def test_catalog_tool_keeps_its_canonical_id_instead_of_becoming_a_proposal() -> None:
    texto = "Semana 1: Implementar servicios con Node.js."
    evidencia = "Implementar servicios con Node.js"
    inicio_herramienta = texto.index("Node.js")
    candidata = {
        "id": "TOOL_NODE",
        "nombre": "Node.js",
        "evidencia_literal": "Node.js",
        "seccion_fuente": "silabo_completo",
        "contexto_fuente": texto,
        "start_pos": inicio_herramienta,
        "end_pos": inicio_herramienta + len("Node.js"),
    }
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Implementar servicios",
                    "competencia_propuesta": "Construcción de software",
                    "contexto_relacion": "Implementar servicios con Node.js.",
                    "herramientas_catalogo": [
                        {
                            "id_catalogo": "TOOL_NODE",
                            "start_pos": inicio_herramienta,
                            "end_pos": inicio_herramienta + len("Node.js"),
                            "evidencia_uso": "Node.js",
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(
        bruto, catalog_tool_candidates=(candidata,), source_text=texto
    )

    [paquete] = resultado.paquetes_respaldados
    assert resultado.pendientes == ()
    assert paquete.herramientas_catalogo[0]["id"] == "TOOL_NODE"
    assert paquete.herramientas_propuestas == ()


def test_explicit_uncatalogued_tool_is_a_hitl_proposal_linked_to_competency_and_skill() -> None:
    texto = "Semana 1: Automatizar despliegues con ForgeDeploy."
    evidencia = "Automatizar despliegues con ForgeDeploy"
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Automatizar despliegues",
                    "competencia_propuesta": "Ingeniería de plataformas",
                    "herramientas_propuestas": [
                        {
                            "nombre": "ForgeDeploy",
                            "tipo_ontologia": "software",
                            "seccion_fuente": "programa_semanal",
                            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
                            "evidencia_uso": "ForgeDeploy",
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    [paquete] = resultado.paquetes_respaldados
    assert resultado.pendientes == ()
    assert paquete.habilidad_propuesta == "Automatizar despliegues"
    assert paquete.competencia_propuesta == "Ingeniería de plataformas"
    assert paquete.herramientas_propuestas[0] == {
        "nombre": "ForgeDeploy",
        "tipo_ontologia": "software",
        "estado": "PROPUESTA_HITL",
        "requiere_aprobacion_humana": True,
        "seccion_fuente": "programa_semanal",
        "evidencia_literal": evidencia,
        "start_pos": texto.index(evidencia),
        "end_pos": texto.index(evidencia) + len(evidencia),
        "evidencia_uso": "ForgeDeploy",
    }


@pytest.mark.parametrize("tipo_ontologia", ["libreria", "biblioteca", "library"])
def test_explicit_unknown_library_is_a_hitl_proposal_linked_to_competency_and_skill(
    tipo_ontologia: str,
) -> None:
    texto = "Semana 1: Analizar indicadores con GraphPulse."
    evidencia = "Analizar indicadores con GraphPulse"
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Analizar indicadores",
                    "competencia_propuesta": "Análisis de datos",
                    "herramientas_propuestas": [
                        {
                            "nombre": "GraphPulse",
                            "tipo_ontologia": tipo_ontologia,
                            "seccion_fuente": "programa_semanal",
                            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
                            "evidencia_uso": "con GraphPulse",
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    [paquete] = resultado.paquetes_respaldados
    [propuesta] = paquete.herramientas_propuestas
    assert resultado.pendientes == ()
    assert paquete.competencia_propuesta == "Análisis de datos"
    assert paquete.habilidad_propuesta == "Analizar indicadores"
    assert propuesta["tipo_ontologia"] == "biblioteca"
    assert propuesta["estado"] == "PROPUESTA_HITL"
    assert propuesta["requiere_aprobacion_humana"] is True
    assert "id" not in propuesta
    assert propuesta["evidencia_literal"] == evidencia
    assert propuesta["start_pos"] == texto.index(evidencia)
    assert propuesta["end_pos"] == texto.index(evidencia) + len(evidencia)


@pytest.mark.parametrize("nombre", ["herramientas avanzadas", "algoritmo de Dijkstra"])
def test_rejects_generic_or_algorithm_uncatalogued_tool(nombre: str) -> None:
    texto = f"Semana 1: Aplicar {nombre}."
    evidencia = f"Aplicar {nombre}"
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Aplicar procedimientos",
                    "competencia_propuesta": "Desarrollo de software",
                    "herramientas_propuestas": [
                        {
                            "nombre": nombre,
                            "tipo_ontologia": "library",
                            "seccion_fuente": "programa_semanal",
                            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
                            "evidencia_uso": nombre,
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.paquetes_respaldados[0].herramientas_propuestas == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "HERRAMIENTA_NOMBRE_GENERICO"
    ]


def test_rejects_uncatalogued_tool_without_literal_name_evidence() -> None:
    texto = "Semana 1: Automatizar despliegues con una plataforma interna."
    evidencia = "Automatizar despliegues con una plataforma interna"
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Automatizar despliegues",
                    "competencia_propuesta": "Ingeniería de plataformas",
                    "herramientas_propuestas": [
                        {
                            "nombre": "ForgeDeploy",
                            "tipo_ontologia": "software",
                            "seccion_fuente": "programa_semanal",
                            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
                            "evidencia_uso": "plataforma interna",
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert resultado.paquetes_respaldados[0].herramientas_propuestas == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "HERRAMIENTA_CITA_NO_LITERAL"
    ]


def test_prompt_no_hardcodes_named_tools() -> None:
    assert all(
        term.casefold() not in PROMPT_EXTRACCION_CIAR.casefold()
        for term in ("Metasploit", "Node.js", "Git", "SAP S/4HANA")
    )


def test_rechaza_herramienta_generica_y_retiene_paquete_sin_herramientas() -> None:
    texto = "Semana 1: Analiza datos con herramientas avanzadas."
    bruto = {
        "text": texto,
        "extractions": [
            _paquete(
                texto,
                herramientas=[
                    {
                        "nombre": "herramientas avanzadas",
                        "tipo_ontologia": "software",
                        "seccion_fuente": "programa_semanal",
                        "cita_fuente": {
                            "texto": "herramientas avanzadas",
                            **_span(texto, "herramientas avanzadas"),
                        },
                        "evidencia_uso": "Analiza datos con herramientas avanzadas",
                    }
                ],
            )
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert len(resultado.paquetes_respaldados) == 1
    assert resultado.paquetes_respaldados[0].herramientas == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "HERRAMIENTA_NOMBRE_GENERICO"
    ]


def test_rechaza_herramienta_fuera_del_programa_semanal_y_retiene_paquete() -> None:
    texto = (
        "[PRIMARY EVIDENCE: PROGRAMA_SEMANAL]\nSemana 1: Analiza datos."
        "\n\n[COMPLEMENTARY CONTEXT: SUMILLA]\nPython."
    )
    bruto = {
        "text": texto,
        "extractions": [
            _paquete(
                texto,
                herramientas=[
                    {
                        "nombre": "Python",
                        "tipo_ontologia": "lenguaje",
                        "seccion_fuente": "programa_semanal",
                        "cita_fuente": {"texto": "Python", **_span(texto, "Python")},
                        "evidencia_uso": "Python",
                    }
                ],
            )
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert len(resultado.paquetes_respaldados) == 1
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "HERRAMIENTA_SECCION_NO_ADMITIDA"
    ]


@pytest.mark.parametrize(
    ("nombre", "tipo_ontologia", "codigo"),
    [
        ("Lecturas guiadas", "software", "HERRAMIENTA_NOMBRE_GENERICO"),
        ("Diagrama UML", "software", "HERRAMIENTA_NOMBRE_GENERICO"),
        ("Python", "metodo", "HERRAMIENTA_TIPO_NO_ADMITIDO"),
    ],
)
def test_rechaza_herramientas_fuera_de_la_ontologia(
    nombre: str, tipo_ontologia: str, codigo: str
) -> None:
    texto = "Semana 1: Analiza datos con Python."
    bruto = {
        "text": texto,
        "extractions": [
            _paquete(
                texto,
                herramientas=[
                    {
                        "nombre": nombre,
                        "tipo_ontologia": tipo_ontologia,
                        "seccion_fuente": "programa_semanal",
                    }
                ],
            )
        ],
    }

    resultado = adaptar_resultado_langextract(bruto)

    assert len(resultado.paquetes_respaldados) == 1
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [codigo]


@pytest.mark.parametrize(
    "nombre",
    ["StarUML", "PlantUML", "Diagrams.net", "Python", "SAP S/4HANA", "pfSense"],
)
def test_concrete_products_survive_the_generic_name_filter(nombre: str) -> None:
    assert not _nombre_herramienta_generico(nombre)


@pytest.mark.parametrize(
    "nombre",
    [
        "UML",
        "diagrama de clases",
        "Diagramas de secuencia",
        "notación UML",
        "sistema ERP",
        "herramienta especializada",
        "lenguaje de programación",
        "framework de pruebas",
        "estándar de cifrado",
    ],
)
def test_category_names_are_rejected_as_generic(nombre: str) -> None:
    assert _nombre_herramienta_generico(nombre)


def _candidata_node(texto: str) -> dict[str, object]:
    inicio = texto.index("Node.js")
    return {
        "id": "TOOL_NODE",
        "nombre": "Node.js",
        "evidencia_literal": "Node.js",
        "seccion_fuente": "silabo_completo",
        "contexto_fuente": texto,
        "start_pos": inicio,
        "end_pos": inicio + len("Node.js"),
    }


def _bruto_con_catalogo(texto: str, evidencia: str, asignaciones: object) -> dict[str, object]:
    inicio = texto.index("Node.js")
    return {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Implementar servicios",
                    "competencia_propuesta": "Desarrollo de software",
                    "contexto_relacion": "Implementar servicios con Node.js.",
                    "herramientas_catalogo": [
                        {
                            "id_catalogo": "TOOL_NODE",
                            "start_pos": inicio,
                            "end_pos": inicio + len("Node.js"),
                            "evidencia_uso": "Node.js",
                        }
                    ]
                    if asignaciones is None
                    else asignaciones,
                },
            }
        ],
    }


def test_benchmark_profile_links_catalog_candidate_instead_of_dropping_it() -> None:
    texto = "Semana 1: Implementar servicios con Node.js."
    evidencia = "Implementar servicios con Node.js"

    resultado = adaptar_resultado_langextract(
        _bruto_con_catalogo(texto, evidencia, asignaciones=None),
        profile="benchmark",
        catalog_tool_candidates=(_candidata_node(texto),),
        source_text=texto,
    )

    [paquete] = resultado.paquetes_respaldados
    assert resultado.pendientes == ()
    assert [herramienta["id"] for herramienta in paquete.herramientas_catalogo] == ["TOOL_NODE"]

def test_benchmark_profile_forces_catalog_linkage_instead_of_plain_name() -> None:
    texto = "Semana 1: Implementar servicios con Node.js."
    evidencia = "Implementar servicios con Node.js"
    bruto = _bruto_con_catalogo(texto, evidencia, asignaciones=[])
    atributos = bruto["extractions"][0]["attributes"]  # type: ignore[index]
    atributos.pop("herramientas_catalogo")
    atributos["herramientas"] = [
        {
            "nombre": "Node.js",
            "tipo_ontologia": "software",
            "seccion_fuente": "programa_semanal",
            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
            "evidencia_uso": "Node.js",
        }
    ]

    resultado = adaptar_resultado_langextract(
        bruto,
        profile="benchmark",
        catalog_tool_candidates=(_candidata_node(texto),),
        source_text=texto,
    )

    [paquete] = resultado.paquetes_respaldados
    assert paquete.herramientas == ()
    assert paquete.herramientas_catalogo == ()
    assert [pendiente.codigo for pendiente in resultado.pendientes] == [
        "HERRAMIENTA_CATALOGO_DEBE_VINCULARSE"
    ]


def test_benchmark_profile_keeps_uncatalogued_tool_as_hitl_proposal() -> None:
    texto = "Semana 1: Automatizar despliegues con ForgeDeploy."
    evidencia = "Automatizar despliegues con ForgeDeploy"
    candidata = _candidata_node("Semana 1: Implementar servicios con Node.js.")
    bruto = {
        "text": texto,
        "extractions": [
            {
                "extraction_class": "paquete_respaldado",
                "extraction_text": evidencia,
                "char_interval": _span(texto, evidencia),
                "attributes": {
                    "habilidad_propuesta": "Automatizar despliegues",
                    "competencia_propuesta": "Ingeniería de plataformas",
                    "contexto_relacion": "Automatizar despliegues con ForgeDeploy.",
                    "herramientas": [
                        {
                            "nombre": "ForgeDeploy",
                            "tipo_ontologia": "software",
                            "seccion_fuente": "programa_semanal",
                            "cita_fuente": {"texto": evidencia, **_span(texto, evidencia)},
                            "evidencia_uso": "con ForgeDeploy",
                        }
                    ],
                },
            }
        ],
    }

    resultado = adaptar_resultado_langextract(
        bruto,
        profile="benchmark",
        catalog_tool_candidates=(candidata,),
        source_text=texto,
    )

    [paquete] = resultado.paquetes_respaldados
    assert paquete.herramientas == ("ForgeDeploy",)
    assert [propuesta["nombre"] for propuesta in paquete.herramientas_propuestas] == [
        "ForgeDeploy"
    ]


def test_benchmark_profile_tolerates_casing_and_spacing_in_usage_evidence() -> None:
    texto = "Semana 1: Implementar servicios con Node.js."
    evidencia = "Implementar servicios con Node.js"
    bruto = _bruto_con_catalogo(
        texto,
        evidencia,
        asignaciones=[
            {
                "id_catalogo": "TOOL_NODE",
                "start_pos": texto.index("Node.js"),
                "end_pos": texto.index("Node.js") + len("Node.js"),
                "evidencia_uso": "  con   NODE.JS ",
            }
        ],
    )

    resultado = adaptar_resultado_langextract(
        bruto,
        profile="benchmark",
        catalog_tool_candidates=(_candidata_node(texto),),
        source_text=texto,
    )

    [paquete] = resultado.paquetes_respaldados
    assert [herramienta["id"] for herramienta in paquete.herramientas_catalogo] == ["TOOL_NODE"]
