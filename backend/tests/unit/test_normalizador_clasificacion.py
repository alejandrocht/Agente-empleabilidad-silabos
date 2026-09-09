"""Canonical classification and historical payload conversion contracts."""

from __future__ import annotations

import copy

import pytest

from agente.normalizador.silabos import clasificacion
from agente.normalizador.silabos.paquetes import ensamblar_paquetes_chh


@pytest.mark.parametrize("explicit", [False, None])
def test_canonical_presence_wins_over_conflicting_legacy_truthy_flags(explicit):
    row = {
        "propuesta": {"nombre": "Analizar campañas"},
        "auto_deduplicated": True,
        "requiere_decision": True,
        "clasificacion": {"auto_deduplicated": explicit, "requires_human_decision": explicit},
    }
    state = clasificacion.estado_clasificacion(row)
    assert state.auto_deduplicated is False
    assert state.requires_human_decision is False
    assert clasificacion.puede_recibir_decision(row)


@pytest.mark.parametrize("decision", ["ADD", "KEEP_PENDING", "DISCARD"])
def test_legacy_human_decisions_remain_resolved(decision):
    row = {"decision": decision, "estado_resolucion": "PENDIENTE", "auto_deduplicated": None}
    assert not clasificacion.requiere_resolucion_curricular(row)
    assert not clasificacion.estado_clasificacion(row).auto_deduplicated


def test_partial_legacy_spanish_flags_and_none_group_have_explicit_precedence():
    row = {
        "duplicado_exacto": True,
        "grupo_duplicado_exacto": "EXACT_old",
        "posible_duplicado_semantico": True,
        "herramienta_no_relacionada": True,
        "clasificacion": {"exact_duplicate_group": None},
    }
    state = clasificacion.estado_clasificacion(row)
    assert state.exact_duplicate_group is None
    assert state.exact_duplicate
    assert state.semantic_duplicate
    assert state.suspicious_tool
    assert state.requires_human_decision  # Absent legacy field defaults to review, not approval.


def test_package_rules_read_canonical_state_not_legacy_aliases():
    row = {
        "id_ejecucion": "NOR_TEST",
        "carrera": "MARKETING",
        "periodo": "2026-1",
        "id_curso": "CUR_1",
        "id_silabo": "SIL_1",
        "id_habilidad_fuente": "HAB_SRC_1",
        "id_pendiente": "PEN_1",
        "tipo": "habilidad",
        "propuesta": {"nombre": "Analizar campañas"},
        "estado_resolucion": "PENDIENTE",
        "auto_deduplicated": True,
        "clasificacion": {"auto_deduplicated": False, "requires_human_decision": True},
    }
    package = ensamblar_paquetes_chh([row])[0]
    assert package["manual_review_rows"] == ["PEN_1"]
    assert package["alias_ids"] == []


def test_classification_roundtrip_and_representative_do_not_mutate_or_drop_approvals():
    rows = [
        {
            "id_pendiente": "PEN_1",
            "tipo": "habilidad",
            "propuesta": {"nombre": "Analizar campañas"},
            "decision": "ADD",
            "confianza": 0.9,
        },
        {
            "id_pendiente": "PEN_2",
            "tipo": "habilidad",
            "propuesta": {"nombre": "Analizar campañas"},
            "decision": "KEEP_PENDING",
            "confianza": 0.5,
        },
    ]
    original = copy.deepcopy(rows)
    classified = clasificacion.clasificar_propuestas(rows)
    assert rows == original
    assert [r["decision"] for r in classified] == ["ADD", "KEEP_PENDING"]
    assert [clasificacion.estado_clasificacion(r).auto_deduplicated for r in classified] == [
        False,
        True,
    ]
    for row in classified:
        state = clasificacion.estado_clasificacion(row)
        assert state.a_dict() == {key: row[key] for key in state.a_dict()}
    assert clasificacion.clasificar_propuestas(classified) == classified
