"""Integrity gates for the pending, offline Marketing evaluation fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "evaluacion_marketing"


def _load_fixture() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((FIXTURE_DIR / "esquema_caso.json").read_text(encoding="utf-8"))
    lines = (FIXTURE_DIR / "casos.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines if line.strip()]
    return manifest, schema, cases


def _assert_automated_gold_metrics_blocked(
    manifest: dict[str, Any], cases: list[dict[str, Any]]
) -> None:
    """The metric seam fails closed until humans finish and reconcile the fixture."""
    if manifest["status"] == "PENDIENTE_ETIQUETADO_HUMANO" or not cases:
        raise RuntimeError("automated gold metrics are blocked until human labels are reconciled")


def test_fixture_files_are_local_and_pending() -> None:
    manifest, schema, cases = _load_fixture()

    assert {path.name for path in FIXTURE_DIR.iterdir()} == {
        "README.md",
        "manifest.json",
        "casos.jsonl",
        "esquema_caso.json",
    }
    assert schema["required"] == manifest["required_case_fields"]
    assert manifest["status"] == "PENDIENTE_ETIQUETADO_HUMANO"
    assert manifest["target_case_count"] == 36
    assert manifest["labeled_case_count"] == 0
    assert manifest["evaluation"]["automated_metrics_allowed"] is False
    assert cases == []


def test_manifest_sampling_contract_targets_all_cycles_and_adversarial_cases() -> None:
    manifest, _, _ = _load_fixture()
    cycle_counts = manifest["sampling"]["cycle_counts"]

    assert list(cycle_counts) == [f"Ciclo_{index:02d}" for index in range(1, 11)]
    assert sum(cycle_counts.values()) == manifest["target_case_count"] - 4
    assert manifest["adversarial_case_count"] == 4
    assert manifest["sampling"]["domain_minimum"] >= 3
    assert manifest["sampling"]["model_outputs_are_not_selection_or_truth_source"] is True


def test_required_case_fields_cover_source_labels_and_review() -> None:
    manifest, schema, _ = _load_fixture()

    assert set(manifest["required_case_fields"]) == set(schema["required"])
    assert set(schema["properties"]["source"]["required"]) >= {
        "id_habilidad_fuente",
        "id_curso",
        "id_silabo",
        "archivo",
        "evidence",
    }
    assert set(schema["properties"]["expected"]["required"]) >= {
        "outcome",
        "competency",
        "skill",
        "tool",
    }
    assert set(schema["properties"]["labeler"]["required"]) >= {
        "labeler_id",
        "label_source",
    }
    assert "REVIEW_HUMAN" in schema["properties"]["expected"]["properties"]["outcome"]["enum"]


def test_automated_gold_metrics_are_blocked_while_fixture_has_zero_labels() -> None:
    manifest, _, cases = _load_fixture()

    with pytest.raises(RuntimeError, match="blocked"):
        _assert_automated_gold_metrics_blocked(manifest, cases)
