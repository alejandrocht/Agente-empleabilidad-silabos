from __future__ import annotations

from agente.normalizador.silabos.langextract_ciar import construir_ejemplos_langextract


def test_examples_are_synthetic_ciar_rules_not_document_evidence() -> None:
    examples = construir_ejemplos_langextract()

    assert len(examples) == 2
    assert all("Ejemplo sintético CIAR" in example.text for example in examples)
    assert examples[0].extractions[0].extraction_class == "paquete_respaldado"
    assert examples[0].extractions[0].attributes["herramientas"] == ["Python"]
    assert examples[1].extractions[0].extraction_class == "pendiente"
