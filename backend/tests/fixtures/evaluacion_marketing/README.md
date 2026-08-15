# Marketing 2026-1 offline gold-set scaffold

This directory is a **labeling contract**, not a gold set yet. The manifest intentionally remains `PENDIENTE_ETIQUETADO_HUMANO` with zero labeled cases, and `casos.jsonl` is empty. No automated metric may run in this state.

## Human workflow

1. Sample 36 source records with seed `20260812`: three cases for each of `Ciclo_01` through `Ciclo_08`, four for `Ciclo_09` and `Ciclo_10`, while maintaining at least three cases per declared domain. Reserve four adversarial cases: competency mismatch, inflated skill level, unsupported tool, and unsupported/invented evidence.
2. Label source evidence first. Read the original curriculum record and its declared competency before inspecting any candidate output. Record source IDs, file, achievement text, and verbatim evidence in `source`.
3. In pass one, one human labels `expected.competency`, `expected.skill`, optional `expected.tool`, evidence requirements, and `expected.outcome`.
4. In pass two, a different reviewer reconciles the label against the same source evidence. Use `REVIEW_HUMAN` when the source cannot support a unique competency, skill, or tool decision; it is an accepted outcome, not a test failure.
5. Only after reconciliation may a candidate model output be attached outside this fixture and scored. Never copy a v4 LLM decision, confidence, justification, or acceptance state into `expected`.

## Acceptance gates

- All 36 cases exist, are unique, and match the cycle/domain/adversarial quotas in `manifest.json`.
- Every case has source identifiers and at least one evidence item.
- Competency and skill labels are independently human-authored, or the outcome is `REVIEW_HUMAN` with a reason.
- Tools are optional and require evidence of applied use; a mere mention in learning resources is insufficient.
- Every case has an explicit labeler and review status. The second pass must be `RECONCILED` or `REVIEW_HUMAN`.
- Automated metrics remain blocked until all labels are present and the manifest status is changed deliberately in a later work unit.

## Files

- `manifest.json`: target, sampling contract, status, required fields, and metric gate.
- `esquema_caso.json`: JSON Schema contract for future JSONL records.
- `casos.jsonl`: intentionally zero lines until independent human labeling begins.
- `../../unit/test_normalizador_evaluacion_marketing.py`: offline integrity and pending-state gate tests.

The fixture has no network, OpenAI, Neo4j, or external-path dependency.
