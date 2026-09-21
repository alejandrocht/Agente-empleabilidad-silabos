# Offline technical competency benchmark

This directory is a no-network scaffold for future labeled cases. It does not invoke an
LLM, embeddings service, vector database, or live benchmark. Keep cases and predictions as
UTF-8 JSONL so a later run can be reproduced from saved inputs.

## Case JSONL contract

Each case row contains:

- `case_id`: stable unique identifier.
- `career`: display career supplied to the analyst.
- `learning_outcomes`: literal outcome strings used as the evidence authority.
- `catalog_candidates`: the complete compact career-scoped catalog context. Every candidate
  contains only `catalogo_ref`, `nombre`, and `descripcion`.
- `expected.catalogo_refs`: labeled catalog references supported by the outcomes.
- `expected.evidence`: labeled literal evidence fragments.
- `expected.allow_fallback`: whether a no-catalog-reference proposal is acceptable.

The templates currently contain only metadata rows. Replace them with labeled case rows and
saved predictions when benchmark data is available. `cases.schema.json` describes both metadata
and case rows.

## Saved prediction JSONL contract

The evaluator accepts one row per case:

```json
{"case_id":"TCB-001","competencias":[{"catalogo_ref":"CATTEC_abc","evidencia":[{"fuente":"logro","fragmento":"Diseña APIs REST."}]}]}
```

`catalogo_ref` may be `null` for a fallback proposal. A competency is counted as fallback when
its reference is null/empty or its `origen_propuesta` starts with `FALLBACK`. Evidence support is
measured by case-insensitive literal substring matching against that case's `learning_outcomes`.
Metadata rows with `{"kind":"metadata",...}` are ignored in both files.

## Deterministic evaluator

From `backend/`, run the offline scaffold with its templates:

```bash
python scripts/benchmark_tecnico.py \
  --cases tests/fixtures/technical_competency_benchmark/cases.template.jsonl \
  --predictions tests/fixtures/technical_competency_benchmark/predictions.template.jsonl
```

The CLI emits JSON with catalog-reference recall and precision, expected evidence recall,
evidence support rate, fallback rate, expected fallback case count, fallback match rate, and
`missing_predictions`. Fallback-match rate is computed only over cases with an actual saved
prediction; missing predictions are never treated as correct fallback decisions. Empty case or
prediction files are valid and report `no_cases`/`no_predictions` with null metrics where a
denominator is absent.
Malformed JSONL, missing required fields, duplicate case IDs, and unknown prediction case IDs fail
with an `error:` message and exit code 2. No command in this scaffold makes network calls.
