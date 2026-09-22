# Deduplicate identical technical competency proposals

## Objective

Ensure the technical LLM pipeline emits at most one proposal for each competency name within a syllabus.

## Problem

A single syllabus/content can legitimately produce multiple technical competencies, including multiple proposals associated with the same `catalogo_ref`. The only invalid duplicate is a repeated competency name; catalog reference, description, learning outcomes, evidence, and justification must not prevent removal of that repeated name.

## Scope

- Make the existing analyzer deduplication key use only the normalized syllabus identity and competency name.
- Preserve the first-seen proposal and existing cross-syllabus behavior.
- Add focused regression coverage for repeated names and for multiple distinct names sharing a catalog reference.

## Constraints

- Do not touch the concurrent `botones fix` surfaces: `backend/agente/normalizador/silabos/aprobaciones_tecnicas.py`, `backend/agente/observabilidad/langsmith.py`, or post-HITL/observability tests.
- Keep Python deterministic and avoid LLM-dependent behavior.
- Keep the patch limited to the analyzer and its focused unit test.

## Tasks

- [x] T1. Make analyzer deduplication use only normalized `id_silabo` and competency name.
- [x] T2. Replace the regression test with repeated-name and same-catalog-reference/different-name cases.
- [x] T3. Run focused static and behavioral checks; record results and leave unrelated concurrent changes untouched.

## Acceptance criteria

1. Two valid LLM proposals with the same normalized name in one syllabus produce exactly one returned proposal.
2. The retained proposal is the first-seen row, including its supporting data and justification.
3. Two different competency names remain separate even when they share a `catalogo_ref`.
4. The model is not retried when valid proposals remain after deduplication.
5. Existing analyzer tests continue to pass.

## Verification

- `cd backend && .venv/bin/python -m pytest tests/unit/test_analista_tecnico.py -q`
- `cd backend && .venv/bin/python -m ruff check agente/normalizador/silabos/analista_tecnico.py tests/unit/test_analista_tecnico.py`
- `cd backend && .venv/bin/python -m mypy agente/normalizador/silabos/analista_tecnico.py --show-error-codes --no-error-summary`
- `git diff --check` for the scoped patch.

## Progress

- Exploration found the shared analyzer seam in `analista_tecnico.py` and confirmed downstream consumers trust its returned list.
- The concurrent session confirmed it does not share the analyzer or analyzer-test files.
- A prior attempt incorrectly made only `logros` order-insensitive; the user clarified that repeated competency names are the only duplicates to remove.
- A single syllabus may produce multiple competencies from one content and multiple competencies may share `catalogo_ref`.
- The corrected identity must use only normalized `id_silabo` and `nombre_competencia`; description and all supporting data do not distinguish duplicates.
- The first materialized proposal is retained; a later repeated name is discarded before counts and persistence.
- Engram mirror: pending because the local Engram provider is unavailable.

## Route

- T1/T2: delegated bounded writer; allowed edit surfaces are the analyzer and its focused unit test.
- T3: delegated verification after the writer returns; parent performs final scoped readback.

## Verification evidence

- Independent verifier: `cd backend && .venv/bin/python -m pytest tests/unit/test_analista_tecnico.py -q` — 18 passed.
- Independent verifier: focused Ruff — passed.
- Independent verifier: focused strict Mypy — passed with no output.
- Independent verifier: scoped `git diff --check` — passed.
- Parent spot check: focused analyzer pytest — 18 passed.
- Native ASSESS was unavailable with empty native output; RDD therefore treated the candidate as unassessable/high and required independent verification, which passed.
- Concurrent `botones fix` surfaces remain excluded; no commit or push is performed here.
- Engram mirror: pending because the local Engram provider is unavailable.

## Next step

No further code changes are pending. The user may stage and commit/push each session's files selectively.
