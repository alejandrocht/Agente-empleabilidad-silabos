from __future__ import annotations

import json

from agente.normalizador.silabos.langextract_ciar import (
    _TIPOS_HERRAMIENTA_ADMITIDOS,
    _habilidad_accion_objeto,
    _nombre_herramienta_generico,
    construir_ejemplos_langextract,
)

_TRANSVERSALES = {
    "resolución de problemas",
    "trabajo en equipo",
    "pensamiento crítico",
    "comunicación efectiva",
}


def _paquetes() -> list[object]:
    return [
        extraction
        for example in construir_ejemplos_langextract()
        for extraction in example.extractions
        if extraction.extraction_class == "paquete_respaldado"
    ]


def test_examples_are_synthetic_ciar_rules_not_document_evidence() -> None:
    examples = construir_ejemplos_langextract()

    assert all("Ejemplo sintético CIAR" in example.text for example in examples)
    clases = {
        extraction.extraction_class
        for example in examples
        for extraction in example.extractions
    }
    assert clases == {"paquete_respaldado", "pendiente"}


def test_examples_cover_the_tool_optional_and_rejected_cases() -> None:
    """Coverage the model needs: tool present, no tool, and a rejected category."""

    paquetes = _paquetes()

    assert any(paquete.attributes.get("herramientas") for paquete in paquetes)
    assert any("herramientas" not in paquete.attributes for paquete in paquetes)
    assert any(
        extraction.extraction_class == "pendiente"
        for example in construir_ejemplos_langextract()
        for extraction in example.extractions
    )


def test_package_examples_never_teach_a_transversal_competency() -> None:
    for paquete in _paquetes():
        competencia = paquete.attributes["competencia_propuesta"]
        assert competencia.casefold() not in _TRANSVERSALES
        assert _habilidad_accion_objeto(paquete.attributes["habilidad_propuesta"])


def test_examples_cover_the_catalog_candidate_contract() -> None:
    """The model must learn to link candidates by id instead of dropping them."""

    catalogo = [
        example
        for example in construir_ejemplos_langextract()
        if "[DETECTED CATALOG TOOL CANDIDATES]" in example.text
    ]

    assert len(catalogo) == 1
    example = catalogo[0]
    [candidata] = json.loads(example.text.split("[DETECTED CATALOG TOOL CANDIDATES]\n", 1)[1])
    [extraccion] = example.extractions
    [asignada] = extraccion.attributes["herramientas_catalogo"]

    assert asignada["id_catalogo"] == candidata["id"]
    assert (asignada["start_pos"], asignada["end_pos"]) == (
        candidata["start_pos"],
        candidata["end_pos"],
    )
    assert (
        example.text[asignada["start_pos"] : asignada["end_pos"]]
        == candidata["evidencia_literal"]
    )
    assert asignada["evidencia_uso"] in candidata["contexto_fuente"]
    assert candidata["nombre"] in extraccion.attributes["contexto_relacion"]


def test_tool_examples_match_the_strict_contract() -> None:
    """Every few-shot tool must survive the same validator the runner applies."""

    for example in construir_ejemplos_langextract():
        for extraction in example.extractions:
            for herramienta in extraction.attributes.get("herramientas", ()):
                assert set(herramienta) == {
                    "nombre",
                    "tipo_ontologia",
                    "seccion_fuente",
                    "cita_fuente",
                    "evidencia_uso",
                }
                assert herramienta["tipo_ontologia"] in _TIPOS_HERRAMIENTA_ADMITIDOS
                assert herramienta["seccion_fuente"] == "programa_semanal"
                assert not _nombre_herramienta_generico(herramienta["nombre"])

                cita = herramienta["cita_fuente"]
                inicio, fin = cita["start_pos"], cita["end_pos"]
                assert example.text[inicio:fin] == cita["texto"]
                assert herramienta["evidencia_uso"] in cita["texto"]
                # The tool citation must overlap the package's primary evidence.
                assert cita["texto"] == extraction.extraction_text
