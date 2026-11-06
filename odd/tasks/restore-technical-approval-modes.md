# Restore technical approval modes

Status: verified locally; not delivered
Repository: Agente-empleabilidad-silabos

## Objective
Human mode holds technical proposals for explicit decisions; automatic mode approves eligible LLM proposals and materializes safe CSV outputs without manual decisions. Existing executions lacking a catalog path must still be able to accept valid new proposals using the packaged official catalog and persistent ID registry. Preserve existing uncommitted user work and do not publish.

## Evidence and constraints
- HEAD 09f86e1 includes HITL event logging but local uncommitted catalog/registry changes are not delivered.
- Existing backend and frontend scoped tests pass but omit an old-manifest missing-catalog acceptance case.
- An ignored local manifest lacks `hitl` and `ruta_catalogo_tecnico`; the exact error reported matches the committed baseline, not the uncommitted updated message. No backend/frontend process listens on common ports at inspection time.
- Keep safety gates, unique stable IDs, and rollback behavior. No change to user-owned runtime data. No commit without explicit user authorization (higher safety rule).
- TDD mode: regression-first debugging; runner backend `.venv/bin/python -m pytest -p no:cacheprovider -q`, frontend `./node_modules/.bin/vitest run`. Target ~150 authored changed lines; no delivery.
- Route: delegated bounded writer for multi-file implementation and tests; independent verifier for additional checks.
- Engram mirror `odd/restore-technical-approval-modes/tasks` pending because the local Engram provider is unavailable.

## Tasks
- [x] T1 Reproduce and fix approval of new technical proposals when a persisted manifest omits the catalog path. RED: API 422 for missing ref; GREEN: legacy manifest API ADD produced safe CSV and persistent ID. Workflow suite 12 passed; scoped Ruff passed. Existing rollback test passed. No commit, per safety policy.
- [x] T2 Verify both HITL modes end-to-end with new executions: human mode remains pending; automatic mode ADDs even a new LLM proposal without catalogo_ref, creates stable HAB_TEC ID and CSV. New end-to-end auto-mode test passed; existing manual-mode test passed; workflow and execution suites 32 passed, Ruff passed. Frontend focused tests previously passed (33) before this backend-only change.
- [x] T3 Reconcile diff, confirm preserved local work and report runtime restart/deployment requirement. Independent verifier: backend 69 passed, frontend 29 passed, Ruff clean; scoped diff check clean. No process listening on common ports during inspection. Existing dirty files preserved; no commit/push. No live-browser or real-LLM run performed.

## Delivery limitations and next step
Native review INSPECT stopped before START on intended-untracked selection; the tracked candidate also contains many unrelated dirty files. Do not start a bundled review or infer approval. These changes are local and uncommitted; `git pull` cannot deliver them. The fallback depends on the locally present but untracked `backend/catalogos/carrera_competencia_oficial.csv`, plus existing tracked XLSX. The other pre-existing local settings/registry modifications are also required for this behavior. Before any future delivery, explicitly review/include those dependencies and get authorization for commit/push. Restart the backend after installing the entire change; a previously created run lacking `hitl` cannot change mode retroactively, while manual ADD now works for compatible technical proposals. If the runtime still shows the exact old error message, it is running old code. Live-browser/real-LLM deployment checks remain unverified. The Engram mirror is pending because its provider could not initialize.
