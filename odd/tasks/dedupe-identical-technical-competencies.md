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

## Reopened: persisted proposal boundary

The user supplied a post-fix screenshot showing two identical technical competency cards under different courses. The analyzer regression remains green, but a screenshot-equivalent probe against `_filas_actuales` fails because the approval boundary trusts duplicate persisted rows.

### Follow-up tasks

- [x] T4. Reproduce duplicate cards at the approval API boundary with normalized-equivalent names.
- [x] T5. Canonicalize persisted technical proposals by normalized name, preserving the first proposal and keeping discarded duplicates audit-only.
- [x] T6. Add API-boundary regression coverage and run focused verification.
- [x] T7. Commit and push only the scoped fix to `test/local-llm-technical-pipeline`.

### Follow-up route

- Low-cost Gemini delegation was attempted but unavailable in this environment; the bounded fix proceeds inline.
- Scoped files: `backend/agente/normalizador/silabos/aprobaciones_tecnicas.py`, `backend/tests/unit/test_post_hitl_workflow.py`, and this task document.
- The concurrent analyzer/settings work reported by another session does not overlap these files.

### Follow-up verification evidence

- Red probe before the fix: `_filas_actuales` exposed two cards for normalized-equivalent persisted names.
- Focused API regressions: `2 passed in 2.21s`.
- Full post-HITL suite: `6 passed in 2.26s`.
- Focused Ruff: passed.
- Focused Mypy: passed with exit code 0.
- Scoped `git diff --check`: passed.
- Independent verification found and then confirmed the correction for legacy journal decisions referencing hidden duplicates; genuine orphan IDs still return HTTP 422.
- Work-unit commit `669674a` (`fix(normalizer): dedupe persisted proposals`) was pushed to `origin/test/local-llm-technical-pipeline`.
- Native review was unavailable for this isolated commit because unrelated concurrent working-tree changes caused committed-range candidate projection drift; no lineage was created. Independent verification and focused checks passed.
