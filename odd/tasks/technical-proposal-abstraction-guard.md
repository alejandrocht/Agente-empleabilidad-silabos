# Technical Proposal Abstraction Guard

## Objective

Prevent technical competency proposals from presenting a syllabus learning outcome verbatim as if it were a normalized competency, while preserving literal source evidence for human review.

## Problem

The technical analyzer validates that `logros` and `evidencia` point to source learning outcomes, but it does not validate that `nombre_competencia` and `descripcion_breve_competencia` are an abstraction. The prompt also emphasizes literal outcome copying without explicitly separating evidence fields from the proposed competency label. As a result, new LLM proposals can echo or lightly paraphrase the syllabus sentence and reach the review queue.

## Why

A proposal that only repeats its evidence adds no semantic normalization and makes the LLM stage misleading. Literal evidence must remain auditable, but it must never be displayed as the competency itself. Invalid outputs should be rejected deterministically and leave the technical release gate blocked rather than creating a plausible-looking false competency.

## Scope

- `backend/agente/normalizador/silabos/analista_tecnico.py`
- `backend/tests/unit/test_analista_tecnico.py`

The parallel `botones fix` session owns `backend/agente/normalizador/silabos/aprobaciones_tecnicas.py`, `backend/agente/api/normalizador.py`, and LangSmith observability files. Do not edit those surfaces.

## Constraints

- Keep full learning-outcome text only in `logros` and `evidencia`.
- Preserve catalog-backed proposals: catalog names and descriptions are canonical and are not generated echoes.
- Do not invent deterministic competency labels from source prose.
- If the model still returns a literal new proposal after one clarification retry, record an auditable warning and produce no proposal for that syllabus so the existing gate can block it.
- Preserve unrelated working-tree changes.
- Technical artifacts remain in English; existing Spanish UI/source evidence remains unchanged.

## Tasks

- [x] **TPA-1 — Add abstraction contract and deterministic echo guard**
  - Strengthened the system/clarification prompt to distinguish evidence from the competency abstraction.
  - Rejects new proposals whose name or description is an exact or high-overlap restatement of a source learning outcome.
  - Records a syllabus-scoped warning for rejected literal proposals.

- [x] **TPA-2 — Remove misleading literal fallback**
  - Removed the fallback path that displayed a source learning outcome as a competency description.
  - Catalog proposals and valid abstract LLM proposals remain pending for explicit human review.

- [x] **TPA-3 — Add regression coverage**
  - Added coverage for exact/near-verbatim echoes, valid concise abstractions, catalog-backed acceptance, retry behavior, warning output, and no misleading fallback.
  - Updated affected fallback expectations and warning assertions.

- [x] **TPA-4 — Verify focused analyzer behavior**
  - Focused analyzer tests and the scoped diff check pass; the final reread found only the two authorized source/test files changed by this feature.

## Acceptance Criteria

- A proposal whose new competency name is the full learning outcome never reaches `propuestas_tecnicas.jsonl`.
- A proposal whose description is a near-verbatim restatement is rejected even when its evidence is valid.
- A concise abstraction backed by literal evidence remains pending for HITL review.
- Catalog-backed proposals retain the catalog's canonical name and description.
- When both model attempts fail the abstraction guard, the syllabus receives an audit warning and no misleading fallback proposal.
- Focused analyzer tests pass.

## Verification

- Focused command: `cd backend && .venv/bin/python -m pytest tests/unit/test_analista_tecnico.py -q`
- Structural check: `git diff --check`
- Parent reread of both authorized files after delegated writer completion.
- Writer validation: `cd backend && .venv/bin/python -m pytest tests/unit/test_analista_tecnico.py -q` → 17 passed; scoped `git diff --check` passed.
- Independent verifier observed the same 17 passing tests and clean diff check; it marked the original candidate blocked only because an external formatter changed the test file before its run. Parent spot-check on the current tree reproduced 17 passed in 1.10s and a clean scoped diff check.
- Native review for the shared current tree completed with an approved receipt; one informational warning targeted unrelated `backend/tests/unit/test_langsmith.py`.


## Progress

- Diagnosis completed from screenshots and source inspection.
- Parallel edit surface confirmed with `botones fix`.
- Feature document created before source edits; Engram mirror pending because the local provider is unavailable.
- Delegated writer completed TPA-1 through TPA-3; reported 17 focused analyzer tests passing and `git diff --check` passing.
- Parent reread the post-writer source/test diff; the parallel session's files remain outside this feature's edit surface.
- TPA-4 complete. Work-unit commit `f4ed287` (`fix(normalizer): reject literal proposal echoes`) contains only this feature's analyzer, tests, and task document; the user's parallel `botones fix` session remains outside its edit surface.
