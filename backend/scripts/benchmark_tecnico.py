#!/usr/bin/env python3
"""Evaluate saved technical-competency benchmark cases without an LLM or network."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_CASE_FIELDS = frozenset(
    {"case_id", "career", "learning_outcomes", "catalog_candidates", "expected"}
)
_CANDIDATE_FIELDS = frozenset({"catalogo_ref", "nombre", "descripcion"})
_EXPECTED_FIELDS = frozenset({"catalogo_refs", "evidence", "allow_fallback"})
_METADATA_FIELDS = frozenset({"kind", "description"})


def _nonempty_string(value: object, field: str, line_number: int, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}:{line_number}: {field} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field: str, line_number: int, source: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{source}:{line_number}: {field} must be an array of strings")
    return [item.strip() for item in value if item.strip()]


def _reject_unexpected_fields(
    value: Mapping[str, object], allowed: frozenset[str], label: str, line_number: int, source: str
) -> None:
    unexpected = sorted(set(value) - allowed)
    if unexpected:
        names = ", ".join(unexpected)
        raise ValueError(f"{source}:{line_number}: unexpected {label} field(s): {names}")


def _validate_metadata(
    value: Mapping[str, object], line_number: int, source: str
) -> dict[str, Any]:
    _reject_unexpected_fields(value, _METADATA_FIELDS, "metadata", line_number, source)
    if value.get("kind") != "metadata":
        raise ValueError(f"{source}:{line_number}: unsupported kind {value.get('kind')!r}")
    description = _nonempty_string(value.get("description"), "description", line_number, source)
    return {"kind": "metadata", "description": description}


def _validate_case(value: object, line_number: int, source: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{source}:{line_number}: case must be a JSON object")
    if "kind" in value:
        if value.get("kind") == "metadata":
            return _validate_metadata(value, line_number, source)
        raise ValueError(f"{source}:{line_number}: unsupported kind {value.get('kind')!r}")
    _reject_unexpected_fields(value, _CASE_FIELDS, "case", line_number, source)
    case = dict(value)
    case["case_id"] = _nonempty_string(case.get("case_id"), "case_id", line_number, source)
    case["career"] = _nonempty_string(case.get("career"), "career", line_number, source)
    case["learning_outcomes"] = _string_list(
        case.get("learning_outcomes"), "learning_outcomes", line_number, source
    )
    candidates = case.get("catalog_candidates")
    if not isinstance(candidates, list):
        raise ValueError(f"{source}:{line_number}: catalog_candidates must be an array")
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError(f"{source}:{line_number}: catalog candidate must be an object")
        _reject_unexpected_fields(
            candidate, _CANDIDATE_FIELDS, "catalog candidate", line_number, source
        )
        for field in ("catalogo_ref", "nombre", "descripcion"):
            _nonempty_string(
                candidate.get(field), f"catalog_candidates[].{field}", line_number, source
            )
    expected = case.get("expected")
    if not isinstance(expected, Mapping):
        raise ValueError(f"{source}:{line_number}: expected must be an object")
    _reject_unexpected_fields(expected, _EXPECTED_FIELDS, "expected", line_number, source)
    case["expected"] = {
        "catalogo_refs": _string_list(
            expected.get("catalogo_refs"), "expected.catalogo_refs", line_number, source
        ),
        "evidence": _string_list(
            expected.get("evidence"), "expected.evidence", line_number, source
        ),
        "allow_fallback": expected.get("allow_fallback", False),
    }
    if not isinstance(case["expected"]["allow_fallback"], bool):
        raise ValueError(f"{source}:{line_number}: expected.allow_fallback must be boolean")
    return case


def _validate_prediction(value: object, line_number: int, source: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{source}:{line_number}: prediction must be a JSON object")
    if "kind" in value:
        if value.get("kind") == "metadata":
            return _validate_metadata(value, line_number, source)
        raise ValueError(f"{source}:{line_number}: unsupported kind {value.get('kind')!r}")
    prediction = dict(value)
    prediction["case_id"] = _nonempty_string(
        prediction.get("case_id"), "case_id", line_number, source
    )
    competencies = prediction.get("competencias")
    if not isinstance(competencies, list):
        raise ValueError(f"{source}:{line_number}: competencias must be an array")
    normalized: list[dict[str, Any]] = []
    for index, competency in enumerate(competencies, start=1):
        if not isinstance(competency, Mapping):
            raise ValueError(f"{source}:{line_number}: competencias[{index}] must be an object")
        catalogo_ref = competency.get("catalogo_ref")
        if catalogo_ref is not None and not isinstance(catalogo_ref, str):
            raise ValueError(
                f"{source}:{line_number}: competencias[{index}].catalogo_ref must be string or null"
            )
        origin = competency.get("origen_propuesta", "")
        if not isinstance(origin, str):
            raise ValueError(
                f"{source}:{line_number}: competencias[{index}].origen_propuesta must be a string"
            )
        evidence = competency.get("evidencia", [])
        if not isinstance(evidence, list):
            raise ValueError(
                f"{source}:{line_number}: competencias[{index}].evidencia must be an array"
            )
        evidence_fragments: list[str] = []
        for evidence_item in evidence:
            if not isinstance(evidence_item, Mapping):
                raise ValueError(f"{source}:{line_number}: competency evidence must be an object")
            fragment = evidence_item.get("fragmento")
            evidence_fragments.append(
                _nonempty_string(
                    fragment,
                    f"competencias[{index}].evidencia[].fragmento",
                    line_number,
                    source,
                )
            )
        normalized.append(
            {
                "catalogo_ref": catalogo_ref.strip() if isinstance(catalogo_ref, str) else None,
                "origen_propuesta": origin,
                "evidence": evidence_fragments,
            }
        )
    prediction["competencias"] = normalized
    return prediction


def load_jsonl(path: Path | str, *, kind: str) -> list[dict[str, Any]]:
    """Load and validate cases or predictions, ignoring optional metadata rows."""

    source = str(path)
    rows: list[dict[str, Any]] = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"{source}: cannot read JSONL: {exc}") from exc
    if kind not in {"cases", "predictions"}:
        raise ValueError(f"unsupported JSONL kind: {kind}")
    validator = _validate_case if kind == "cases" else _validate_prediction
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{source}:{line_number}: invalid JSON: {exc.msg}") from exc
        row = validator(value, line_number, source)
        if row.get("kind") == "metadata":
            continue
        identifier = row["case_id"]
        if identifier in seen:
            raise ValueError(f"{source}:{line_number}: duplicate case_id {identifier!r}")
        seen.add(identifier)
        rows.append(row)
    return rows


def _is_fallback(competency: Mapping[str, Any]) -> bool:
    reference = competency.get("catalogo_ref")
    origin = str(competency.get("origen_propuesta", ""))
    return reference in (None, "") or origin.upper().startswith("FALLBACK")


def _contains_evidence(fragment: str, outcomes: Sequence[str]) -> bool:
    folded = fragment.casefold()
    return bool(folded) and any(folded in outcome.casefold() for outcome in outcomes)


def _evidence_fragments_match(expected: str, predicted: str) -> bool:
    expected_key = expected.strip().casefold()
    predicted_key = predicted.strip().casefold()
    return bool(expected_key and predicted_key) and (
        expected_key in predicted_key or predicted_key in expected_key
    )


def evaluate(
    cases: Sequence[Mapping[str, Any]], predictions: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Return deterministic aggregate metrics for already validated benchmark rows."""

    case_by_id = {str(case["case_id"]): case for case in cases}
    prediction_by_id = {str(prediction["case_id"]): prediction for prediction in predictions}
    unknown = sorted(set(prediction_by_id) - set(case_by_id))
    if unknown:
        raise ValueError(f"predictions reference unknown case_id(s): {', '.join(unknown)}")

    expected_refs = 0
    predicted_refs = 0
    true_positive_refs = 0
    expected_evidence_total = 0
    expected_evidence_matches = 0
    evidence_total = 0
    supported_evidence = 0
    fallback_total = 0
    competency_total = 0
    fallback_expectations = 0
    fallback_matches = 0
    missing_predictions = 0
    evaluated_prediction_cases = 0
    for case_id, case in case_by_id.items():
        expected = case["expected"]
        expected_ref_set = set(expected["catalogo_refs"])
        expected_refs += len(expected_ref_set)
        if expected["allow_fallback"]:
            fallback_expectations += 1
        prediction = prediction_by_id.get(case_id)
        if prediction is None:
            missing_predictions += 1
        else:
            evaluated_prediction_cases += 1
        competencies = prediction["competencias"] if prediction is not None else []
        predicted_evidence = [
            fragment for competency in competencies for fragment in competency["evidence"]
        ]
        expected_evidence = expected["evidence"]
        expected_evidence_total += len(expected_evidence)
        expected_evidence_matches += sum(
            any(_evidence_fragments_match(fragment, predicted) for predicted in predicted_evidence)
            for fragment in expected_evidence
        )
        predicted_case_refs = {
            competency["catalogo_ref"] for competency in competencies if competency["catalogo_ref"]
        }
        predicted_refs += len(predicted_case_refs)
        true_positive_refs += len(predicted_case_refs & expected_ref_set)
        case_has_fallback = False
        for competency in competencies:
            competency_total += 1
            case_has_fallback = case_has_fallback or _is_fallback(competency)
            if _is_fallback(competency):
                fallback_total += 1
            for fragment in competency["evidence"]:
                evidence_total += 1
                try:
                    is_supported = _contains_evidence(fragment, case["learning_outcomes"])
                except (KeyError, TypeError) as exc:
                    raise ValueError(f"invalid case {case_id!r} evidence context") from exc
                try:
                    supported_evidence += int(is_supported)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid evidence result for case {case_id!r}") from exc
        if prediction is not None:
            try:
                fallback_matches += int(case_has_fallback == expected["allow_fallback"])
            except (KeyError, TypeError) as exc:
                raise ValueError(f"invalid case {case_id!r} fallback expectation") from exc

    case_count = len(case_by_id)
    prediction_count = len(prediction_by_id)
    return {
        "cases": case_count,
        "predictions": prediction_count,
        "missing_predictions": missing_predictions,
        "no_cases": case_count == 0,
        "no_predictions": prediction_count == 0,
        "catalog_ref_recall": (true_positive_refs / expected_refs if expected_refs else None),
        "catalog_ref_precision": (true_positive_refs / predicted_refs if predicted_refs else None),
        "expected_evidence_recall": (
            expected_evidence_matches / expected_evidence_total if expected_evidence_total else None
        ),
        "evidence_support_rate": (supported_evidence / evidence_total if evidence_total else None),
        "fallback_rate": fallback_total / competency_total if competency_total else None,
        "fallback_expected_cases": fallback_expectations,
        "fallback_match_rate": (
            fallback_matches / evaluated_prediction_cases if evaluated_prediction_cases else None
        ),
    }


def evaluate_files(cases_path: Path | str, predictions_path: Path | str) -> dict[str, Any]:
    cases = load_jsonl(cases_path, kind="cases")
    predictions = load_jsonl(predictions_path, kind="predictions")
    return evaluate(cases, predictions)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, type=Path, help="Saved benchmark cases JSONL")
    parser.add_argument(
        "--predictions", required=True, type=Path, help="Saved model predictions JSONL"
    )
    args = parser.parse_args(argv)
    try:
        report = evaluate_files(args.cases, args.predictions)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
