from __future__ import annotations

from agente.utils.entity_resolver import available_entity_contracts
from agente.utils.entity_semantics import canonical_id_contract

STATIC_KNOWLEDGE_SCHEMA = {
    "node_props": {
        "Habilidad": ["id_habilidad", "nombre_habilidad"],
        "Competencia": ["id_competencia", "nombre_competencia"],
        "Logros": ["id_logros", "logro"],
    }
}


def test_entity_contracts_follow_the_static_ontology() -> None:
    contracts = available_entity_contracts(STATIC_KNOWLEDGE_SCHEMA)

    assert contracts["competencia_tecnica_id"].label == "Habilidad"
    assert contracts["competencia_tecnica_id"].identifier == "id_habilidad"
    assert contracts["logro_id"].label == "Logros"
    assert contracts["logro_id"].identifier == "id_logros"
    assert contracts["competencia_id"].label == "Competencia"
    assert contracts["competencia_id"].identifier == "id_competencia"


def test_legacy_entity_parameters_normalize_to_the_new_contract() -> None:
    assert canonical_id_contract("competencia_tecnica_id") == ("id_habilidad", "=")
    assert canonical_id_contract("habilidad_id") == ("id_habilidad", "=")
    assert canonical_id_contract("competencia_id") == ("id_competencia", "=")
    assert canonical_id_contract("competencia_ids") == ("id_competencia", "IN")
    assert canonical_id_contract("logro_ids") == ("id_logros", "IN")
    assert canonical_id_contract("herramienta_id") == ("id_logros", "=")
