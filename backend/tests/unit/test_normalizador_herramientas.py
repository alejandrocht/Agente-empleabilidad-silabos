"""Public deterministic tool policy; literals are independent contract examples."""

from __future__ import annotations

import pytest

from agente.normalizador.silabos.herramientas import (
    clave_herramienta_canonica,
    coincide_nombre_herramienta_en_texto,
    herramienta_nueva_evidenciada,
    nombre_herramienta_canonico,
)


@pytest.mark.parametrize(
    ("name", "text", "canonical", "supported"),
    [
        ("MS. Word", "Taller: Microsoft Word.", "MS. Word", False),
        ("excel", "Usa MS Excel; analiza.", "Microsoft Excel", True),
        ("Google Analytics 4", "Google Analytics", "Google Analytics", True),
        ("VTEX", "Implementa VTEX.", "VTEX", True),
        ("VTEX", "Implementa VTEX;", "VTEX", True),
        ("Piktochart", "Implementa Piktochart.", "Piktochart", True),
        ("ms word", "Usa Microsoft Word;", "Microsoft Word", True),
        ("Word", "WordPress", "Microsoft Word", False),
        ("Excel", "Hoja de cálculo", "Microsoft Excel", False),
    ],
)
def test_literal_alias_case_and_punctuation(name, text, canonical, supported):
    # Catalog keys intentionally preserve periods (software names); do not broaden aliases.
    assert nombre_herramienta_canonico(name) == canonical
    assert clave_herramienta_canonica(name) == clave_herramienta_canonica(canonical)
    assert coincide_nombre_herramienta_en_texto(name, text) is supported
    assert (
        herramienta_nueva_evidenciada(
            name,
            "LLM text is not evidence",
            {
                "evidencia_herramientas_candidata": [
                    {
                        "origen": "programa_analitico",
                        "seccion": "programa_analitico",
                        "texto": text,
                    }
                ]
            },
        )
        is supported
    )


@pytest.mark.parametrize("name", ["herramientas digitales", "SQL", "KPI", "ETL"])
def test_generic_and_curricular_concepts_are_not_software(name):
    assert not herramienta_nueva_evidenciada(
        name,
        name,
        {
            "evidencia_herramientas": [
                {
                    "origen": "programa_analitico",
                    "seccion": "programa_analitico",
                    "texto": name,
                }
            ]
        },
    )


def test_only_literal_extracted_program_text_can_evidence_a_new_tool():
    assert not herramienta_nueva_evidenciada("VTEX", "VTEX", {"logro": "VTEX"})
    assert not herramienta_nueva_evidenciada(
        "VTEX",
        "VTEX",
        {
            "evidencia_herramientas_candidata": [],
            "evidencia_herramientas": [
                {
                    "origen": "programa_analitico",
                    "seccion": "programa_analitico",
                    "texto": "VTEX",
                }
            ],
        },
    )
    for texto in (
        "Bibliografía: Manual de Datawrapper.",
        "https://www.datawrapper.de/",
        "Use Data visualization software.",
    ):
        assert not herramienta_nueva_evidenciada(
            "Datawrapper",
            "Datawrapper",
            {
                "evidencia_herramientas": [
                    {
                        "origen": "programa_analitico",
                        "seccion": "programa_analitico",
                        "texto": texto,
                    }
                ]
            },
        )
    assert not herramienta_nueva_evidenciada(
        "VTEX",
        "VTEX",
        {"evidencia_herramientas": [{"texto": "Implementar VTEX."}]},
    )
