# Deduplicate identical technical competency proposals

## Objective

Ensure the technical LLM pipeline emits at most one proposal for each normalized competency name across the complete execution.

## Problem

The same technical competency can be proposed by different syllabi/courses in one extraction. Including `id_silabo` in the deduplication key allowed repeated names such as `Configurar redes informáticas.` to appear as separate cards. A single content may still produce multiple distinct competency names, including names sharing a `catalogo_ref`.

## Scope

- Make the existing analyzer deduplication key use only the normalized competency name globally for the execution.
- Preserve the first-seen proposal across syllabi and prevent a duplicate-only response from triggering an unnecessary LLM retry.
- Add focused regression coverage for cross-syllabus repeated names and multiple distinct names sharing a catalog reference.

## Constraints

- Do not touch the concurrent `botones fix` surfaces: `backend/agente/normalizador/silabos/aprobaciones_tecnicas.py`, `backend/agente/observabilidad/langsmith.py`, or post-HITL/observability tests.
- Keep Python deterministic and avoid LLM-dependent behavior.
- Keep the patch limited to the analyzer and its focused unit test.

## Tasks

- [x] T1. Make analyzer deduplication global by normalized competency name and suppress duplicate-only retries.
- [x] T2. Replace the regression test with cross-syllabus repeated-name and same-catalog-reference/different-name cases.
- [x] T3. Run focused static and behavioral checks; record results and leave unrelated concurrent changes untouched.

## Acceptance criteria

1. Two valid LLM proposals with the same normalized name across different syllabi produce exactly one returned proposal.
2. The retained proposal is the first-seen row, including its supporting data and justification.
3. Two different competency names remain separate even when they share a `catalogo_ref`.
4. A response containing only an already-seen competency does not trigger a clarification retry.
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
- The screenshot confirms the real duplicate occurs across different courses/syllabi, so `id_silabo` must not participate in the duplicate identity.
- The corrected identity must use only the normalized `nombre_competencia`; description and all supporting data do not distinguish duplicates.
- The first materialized proposal is retained globally; a later repeated name is discarded before counts and persistence.
- Duplicate-only responses are valid model output after filtering and must not trigger the semantic clarification retry.
- Engram mirror: pending because the local Engram provider is unavailable.

## Route

- T1/T2: delegated bounded writer; allowed edit surfaces are the analyzer and its focused unit test.
- T3: delegated verification after the writer returns; parent performs final scoped readback.

## Verification evidence

- The supplied screenshot is the concrete reproduction: identical `Configurar redes informáticas.` cards appear under different courses.
- Parent fallback verification: `cd backend && .venv/bin/python -m pytest tests/unit/test_analista_tecnico.py -q` — 18 passed.
- Parent fallback verification: focused Ruff — passed.
- Parent fallback verification: focused strict Mypy — passed with no output.
- Parent fallback verification: scoped `git diff --check` — passed.
- Three independent verifier launches, including a retry after the user reported the agent fixed, were unavailable because the Pi runtime still has a duplicate `ask_user_question` extension registration; this is an environment limitation, not a code failure.
- Concurrent `botones fix` surfaces remain excluded; no commit or push is performed here.
- Engram mirror: pending because the local Engram provider is unavailable.

## Next step

The user should rerun the extraction after this correction is committed and the backend process is restarted; the duplicate name must produce only one card.
