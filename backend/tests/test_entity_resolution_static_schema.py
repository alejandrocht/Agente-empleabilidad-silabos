from __future__ import annotations

from agente.utils.entity_resolver import available_entity_contracts
from agente.utils.entity_semantics import canonical_id_contract


STATIC_KNOWLEDGE_SCHEMA = {
    "node_props": {
        "competencia_tecnica": ["id_habilidad", "nombre_habilidad"],
        "Logros": ["id_herramienta", "nombre_herramienta"],
    }
}


def test_entity_contracts_follow_the_static_ontology() -> None:
    contracts = available_entity_contracts(STATIC_KNOWLEDGE_SCHEMA)

    assert contracts["competencia_tecnica_id"].label == "competencia_tecnica"
    assert contracts["competencia_tecnica_id"].identifier == "id_habilidad"
    assert contracts["logro_id"].label == "Logros"
    assert contracts["logro_id"].identifier == "id_herramienta"


def test_legacy_entity_parameters_normalize_to_the_new_contract() -> None:
    assert canonical_id_contract("competencia_tecnica_id") == ("id_habilidad", "=")
    assert canonical_id_contract("habilidad_id") == ("id_habilidad", "=")
    assert canonical_id_contract("logro_ids") == ("id_herramienta", "IN")
    assert canonical_id_contract("herramienta_id") == ("id_herramienta", "=")
