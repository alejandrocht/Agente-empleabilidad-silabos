# Technical HITL control and execution navigation

Status: complete (frontend delivery and backend observability committed)
Repository: `Agente-empleabilidad-silabos`

## Goal

Make per-execution technical HITL observable at the backend, present its switch inside source loading without numeric labels, and let an execution detail return to `/normalizador`.

## Decisions and constraints

- The switch is local UI state; changing it alone must not trigger an HTTP request. The selected mode is sent when a manual or Cactus execution starts.
- Preserve the backend/API `hitl` values (`0` and `1`) and the safe default (`1`); remove numeric values only from visible UI copy.
- Log the mode when a syllabus execution is accepted and log automatic technical approval outcomes without recording credentials, source contents, or raw exception messages.
- Keep the existing release-gate checks unchanged.
- Preserve unrelated working-tree changes. The user authorized frontend-only delivery; backend HITL observability remains uncommitted/local and is excluded from that delivery.
- TDD: strict RED → GREEN → REFACTOR, carried forward from the user's explicit instruction. Runners: backend pytest; frontend Vitest.
- No `CONTEXT.md` or ADR files were found in the repository.
- Forecast: approximately 100 authored changed lines, excluding generated files. Delivery strategy: `ask-on-risk`.

## Tasks

1. **Backend HITL observability** — completed. Added structured acceptance and automatic-approval outcome events, with exception-type-only failure logs and focused regression coverage.
2. **Source-panel HITL control** — completed. Moved the switch into `Carga de fuente`, removed numeric display, and preserved payload/default/restoration behavior.
3. **Execution return navigation** — completed. Added an accessible top navigation link to `/normalizador`, present while loading, on errors, and after load.
4. **Final verification and review routing** — completed. The user-authorized frontend delivery is recorded by `b54ff8d` (`refactor(frontend): simplify normalizer panel`), containing only `NormalizadorPanel.jsx` and its test, and `e6798eb` (`feat(frontend): add execution return link`), containing only the execution detail component and its test. Both are on `origin/test/local-llm-technical-pipeline` at tip `e6798eb0a59ddb0b2f0c138dc070126aceb5e498`. Focused frontend suites passed 36/36 and scoped diff checks passed. Backend HITL observability remains uncommitted/local and was excluded by the user's frontend-only scope. No native review occurred.

## Allowed code edit surfaces

- `backend/agente/normalizador/ejecuciones.py`
- `backend/tests/unit/test_normalizador_ejecuciones.py`
- `frontend/src/components/NormalizadorPanel.jsx`
- `frontend/src/components/NormalizadorPanel.test.jsx`
- `frontend/src/components/InspeccionEjecucionNormalizador.jsx`
- `frontend/src/components/InspeccionEjecucionNormalizador.test.jsx`

The parent owns updates to this task document, Engram, and the visible `todo` projection. Do not modify the shared logging module or unrelated dirty files.

## Verification

- `cd backend && python -m pytest tests/unit/test_normalizador_ejecuciones.py -q`
- `cd backend && ruff check agente/normalizador/ejecuciones.py tests/unit/test_normalizador_ejecuciones.py`
- `cd frontend && npm test -- src/components/NormalizadorPanel.test.jsx src/components/InspeccionEjecucionNormalizador.test.jsx`
- `cd frontend && npm run build`

Run focused tests before each implementation change for RED, after the change for GREEN, and use the applicable focused check for REFACTOR. Report every command and its observed result. Do not expand into the unrelated full-API polling timing failure.

## Route and evidence

- ODD, delegated direct implementation; no SDD/OpenSpec artifacts.
- Mapping trigger: work spans backend flow, structured logger, two UI components, route, and tests. The initial read-only mapper failed, then resumed and returned the source map.
- The session root is a parent Git repository containing the target repository as a nested gitlink. The subagent worktree selector rejected the nested repository as belonging to the session clone; use the default session root, prefix allowed edit surfaces with `Agente-empleabilidad-silabos/`, and run commands from that nested project. Do not modify the parent repository.
- Writer trigger: each implementation task touches multiple non-trivial source/test files. Use one bounded writer at a time with exact task-specific edit surfaces.
- Verification: writer runs its exact task-scoped commands; parent reconciles outcomes and performs required spot-check/review routing.
- Frontend delivery evidence: `b54ff8d` (`refactor(frontend): simplify normalizer panel`) contains only `NormalizadorPanel.jsx` and its test; `e6798eb` (`feat(frontend): add execution return link`) contains only the execution detail component and its test. Both are on `origin/test/local-llm-technical-pipeline` at tip `e6798eb0a59ddb0b2f0c138dc070126aceb5e498`. Backend HITL observability remains uncommitted/local and was excluded by the user's frontend-only scope. No native review occurred.

## Evidence log

- Initial exploration confirmed `NormalizadorPanel.jsx` changes only local state on click; the backend receives `hitl` in the subsequent manual/Cactus start request.
- `GestorEjecuciones._finalizar()` reads the persisted manifest and runs `_auto_aprobar_tecnicas()` only for `hitl="0"` terminal syllabus executions.
- The normalizer detail is rendered by `frontend/app/[id_ejecucion]/page.js`; the target panel route is `frontend/app/normalizador/page.js`.
- Task 1 TDD evidence: focused tests were red before implementation; afterward `python -m pytest tests/unit/test_normalizador_ejecuciones.py -q` passed (19 tests) and scoped Ruff passed.
- Task 1 changed 210 lines total across its implementation and tests; Task 2 changed 65 lines across the panel and tests; Task 3 changed 64 lines across the detail component and tests (339 authored lines total).
- Task 2 TDD evidence: two expected test failures after test-first edits, then `npm test -- src/components/NormalizadorPanel.test.jsx` passed (19 tests); `git diff --check` passed.
- Task 3 TDD evidence: navigation test was red before the component change; afterward `npm test -- src/components/InspeccionEjecucionNormalizador.test.jsx` passed (15 tests) and `npm run build` passed with an existing package-lock tracing warning.
- Final verification evidence: the focused frontend suites passed 36/36, and scoped diff checks passed. The frontend-only delivery was recorded in `b54ff8d` and `e6798eb`, both present on `origin/test/local-llm-technical-pipeline` at tip `e6798eb0a59ddb0b2f0c138dc070126aceb5e498`. Backend HITL observability remains uncommitted/local and was excluded by the user's scope.
- Next build warning: ignored `/Users/alejandromcht/package-lock.json` outside the nested repository and recommended configuring `outputFileTracingRoot`; build still passed.
- Native review did not occur. This documentation update does not claim review activity; it records only the user-authorized frontend delivery and the excluded uncommitted/local backend observability.
