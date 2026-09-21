from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

benchmark_tecnico = importlib.import_module("scripts.benchmark_tecnico")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _case(case_id: str = "TCB-001", *, allow_fallback: bool = False) -> dict[str, object]:
    return {
        "case_id": case_id,
        "career": "Ingeniería de Sistemas",
        "learning_outcomes": ["Diseña APIs REST para sistemas mantenibles."],
        "catalog_candidates": [
            {
                "catalogo_ref": "CATTEC_API",
                "nombre": "Diseñar APIs REST",
                "descripcion": "Diseñar interfaces para sistemas.",
            }
        ],
        "expected": {
            "catalogo_refs": [] if allow_fallback else ["CATTEC_API"],
            "evidence": ["Diseña APIs REST"],
            "allow_fallback": allow_fallback,
        },
    }


def test_evaluate_reports_catalog_evidence_and_fallback_metrics(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    _write_jsonl(cases_path, [_case()])
    _write_jsonl(
        predictions_path,
        [
            {
                "case_id": "TCB-001",
                "competencias": [
                    {
                        "catalogo_ref": "CATTEC_API",
                        "nombre_competencia": "Diseñar APIs REST",
                        "descripcion_breve_competencia": "Diseñar interfaces para sistemas.",
                        "logros": ["Diseña APIs REST para sistemas mantenibles."],
                        "evidencia": [{"fuente": "logro", "fragmento": "Diseña APIs REST"}],
                        "id_propuesta": "PROP_TEC_123",
                    }
                ],
            }
        ],
    )

    report = benchmark_tecnico.evaluate_files(cases_path, predictions_path)

    assert report == {
        "cases": 1,
        "predictions": 1,
        "missing_predictions": 0,
        "no_cases": False,
        "no_predictions": False,
        "catalog_ref_recall": 1.0,
        "catalog_ref_precision": 1.0,
        "expected_evidence_recall": 1.0,
        "evidence_support_rate": 1.0,
        "fallback_rate": 0.0,
        "fallback_expected_cases": 0,
        "fallback_match_rate": 1.0,
    }


def test_evaluate_accepts_empty_scaffold_and_reports_no_work(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    _write_jsonl(
        cases_path,
        [{"kind": "metadata", "description": "future labels"}],
    )
    predictions_path.write_text("", encoding="utf-8")

    report = benchmark_tecnico.evaluate_files(cases_path, predictions_path)

    assert report["no_cases"] is True
    assert report["no_predictions"] is True
    assert report["missing_predictions"] == 0
    assert report["catalog_ref_recall"] is None
    assert report["catalog_ref_precision"] is None
    assert report["expected_evidence_recall"] is None
    assert report["evidence_support_rate"] is None
    assert report["fallback_match_rate"] is None


def test_evaluate_counts_fallback_and_rejects_unsupported_evidence(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    _write_jsonl(cases_path, [_case(allow_fallback=True)])
    _write_jsonl(
        predictions_path,
        [
            {
                "case_id": "TCB-001",
                "competencias": [
                    {
                        "catalogo_ref": None,
                        "origen_propuesta": "FALLBACK_EVIDENCIA",
                        "evidencia": [{"fuente": "logro", "fragmento": "No aparece literalmente"}],
                    }
                ],
            }
        ],
    )

    report = benchmark_tecnico.evaluate_files(cases_path, predictions_path)

    assert report["fallback_expected_cases"] == 1
    assert report["expected_evidence_recall"] == 0.0
    assert report["fallback_rate"] == 1.0
    assert report["evidence_support_rate"] == 0.0
    assert report["fallback_match_rate"] == 1.0


def test_missing_prediction_is_not_counted_as_a_fallback_match(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    _write_jsonl(cases_path, [_case(), _case("TCB-002")])
    _write_jsonl(predictions_path, [{"case_id": "TCB-001", "competencias": []}])

    report = benchmark_tecnico.evaluate_files(cases_path, predictions_path)

    assert report["missing_predictions"] == 1
    assert report["fallback_match_rate"] == 1.0


def test_load_jsonl_fails_clearly_on_malformed_input(tmp_path: Path) -> None:
    path = tmp_path / "malformed.jsonl"
    path.write_text('{"case_id":\n', encoding="utf-8")

    with pytest.raises(ValueError, match=r"malformed\.jsonl:1: invalid JSON"):
        benchmark_tecnico.load_jsonl(path, kind="cases")


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"kind": "metadata", "description": ""}, "description"),
        ({"kind": "metadata", "description": "ok", "extra": True}, "unexpected metadata"),
        ({"kind": "unsupported", "description": "ok"}, "unsupported kind"),
        ({**_case(), "extra": True}, "unexpected case"),
        (
            {
                **_case(),
                "catalog_candidates": [
                    {"catalogo_ref": "CAT", "nombre": "N", "descripcion": "D", "extra": True}
                ],
            },
            "unexpected catalog candidate",
        ),
        (
            {**_case(), "expected": {"catalogo_refs": [], "evidence": [], "extra": True}},
            "unexpected expected",
        ),
    ],
)
def test_case_validation_matches_schema(
    tmp_path: Path, row: dict[str, object], message: str
) -> None:
    path = tmp_path / "invalid.jsonl"
    _write_jsonl(path, [row])

    with pytest.raises(ValueError, match=message):
        benchmark_tecnico.load_jsonl(path, kind="cases")


def test_cli_fails_on_unknown_prediction_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases_path = tmp_path / "cases.jsonl"
    predictions_path = tmp_path / "predictions.jsonl"
    _write_jsonl(cases_path, [_case()])
    _write_jsonl(predictions_path, [{"case_id": "UNKNOWN", "competencias": []}])

    assert (
        benchmark_tecnico.main(["--cases", str(cases_path), "--predictions", str(predictions_path)])
        == 2
    )
    assert "unknown case_id" in capsys.readouterr().err
