# Per-Execution HITL Toggle and Auto-Approval

## Goal

Add a per-execution HITL switch to the syllabus normalizer. `HITL=1` (default) keeps the current human-review flow. `HITL=0` automatically records `ADD` for valid technical proposals and rematerializes the canonical CSVs, without bypassing any other release-gate blocker.

## Decisions and constraints

- The user selected automatic `ADD` for valid proposals when HITL is off.
- Scope is per execution; default to `1` for backward compatibility and safety.
- Reuse the existing technical decision journal and approval/materialization path; retain an auditable system actor/reason.
- HITL off does not disable LLM analysis or weaken structural, extraction-coverage, evidence, or import checks. CSV publication/download still requires `ALLOW_IMPORT`.
- If automatic approval fails, fail closed and leave pending proposals available for manual recovery.
- Preserve all unrelated worktree changes. Do not edit the peer-owned CSV/importer paths. The user later authorized pushing this feature branch; do not include unrelated worktree changes. Native review remains unnecessary.

## Tasks

- [x] **HITL-1 — Persist the execution-level API choice**
  - Accept only `0` or `1` on manual-file and Cactus execution endpoints, defaulting to `1`.
  - Persist the normalized choice in execution parameters. Add focused request-contract tests.
  - Evidence: RED reproduced the missing `hitl` parameter; focused tests passed 6/6 after implementation; independent verification passed 6/6 and scoped `git diff --check` was clean.

- [x] **HITL-2 — Automatically ADD valid proposals without weakening the gate**
  - After a terminal syllabus run with `hitl=0`, batch `ADD` only for validated pending proposals through the existing approval journal/materialization flow.
  - Preserve non-approval blockers across rematerialization, including incomplete Cactus extraction and structural validation failures. Record an actionable warning and keep the gate blocked if auto-approval fails.
  - Add regression tests for successful auto-ADD, auditable decisions, CSV availability only when the full gate allows it, and persistence of unrelated blockers.
  - Evidence: stale `UNLINKED_SOURCE_OUTCOME` regression observed RED before filtering recomputed blockers; focused post-HITL suite passed 10/10, Ruff and scoped `git diff --check` passed independently.

- [x] **HITL-3 — Add the accessible UI switch and document behavior**
  - Add an accessible `1`/`0` switch to the normalizer form, default it to `1`, restore it from execution parameters, and send it for both file and Cactus runs.
  - Add component tests plus request-helper payload tests in `frontend/src/api/normalizador.test.js`; document per-run behavior and release-gate semantics in the backend README.
  - Evidence: frontend API/component tests passed 23/23; Next production build and scoped diff check passed. Switch exposes `role="switch"`, checked state, text value, visible focus, and enabled/disabled cursor states.

## Progress

- Work-unit commit: `040c893` (`feat(normalizer): add per-run HITL switch`).
- HITL-1, HITL-2, and HITL-3 are complete; implementation commit 040c893 is created and pending push. Unrelated worktree changes remain untouched.
- The focused backend API contract (6 tests), post-HITL workflow (10 tests), frontend API/component tests (23 tests), Ruff, scoped diff checks, and Next production build passed.
- Engram mirror writes failed because the configured local Engram service cannot resolve its identity; this file remains the task source of truth.

## Verification

- Strict TDD: observe focused RED before each implementation task, then GREEN and proportionate refactoring.
- Current unrelated blocker: the full `test_normalizador_api.py` file reports 19 passed and one failure in `test_inicia_y_consulta_ejecucion_de_silabos`; it remains `limpiando` after the test's one-second polling window. An independent rerun reproduced the timing-sensitive failure, which is already documented in `odd/tasks/technical-post-hitl-repair.md`. The focused HITL tests pass; do not expand this feature to change the unrelated polling behavior.
- Backend: `cd backend && .venv/bin/python -m pytest tests/unit/test_normalizador_api.py tests/unit/test_post_hitl_workflow.py -q`
- Frontend: `cd frontend && npm test -- src/components/NormalizadorPanel.test.jsx`
- Run Ruff and scoped `git diff --check` for changed paths. Record any unavailable or failed checks; do not commit or push.

## Memory

- Engram task mirror requested at `odd/toggle-hitl-autoapproval/tasks`; the configured local Engram service was unavailable, so this file is the durable task record.
