from __future__ import annotations

from types import SimpleNamespace

import pytest

from agente.normalizador.silabos.langextract_ciar import (
    PROMPT_EXTRACCION_CIAR,
    DocumentoRazonadoCIAR,
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
