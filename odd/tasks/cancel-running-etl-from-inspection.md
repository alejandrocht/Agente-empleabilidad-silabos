# Cancel running ETL from its inspection page

Status: history navigation committed/pushed; inspector cancel/HITL remains local pending 404 diagnosis
Branch: test/local-llm-technical-pipeline

## Goal
The normalizer already has `POST /ejecuciones/{id}/cancelar` and a button on its entry form, but navigation to `/{id}` mounts `InspeccionEjecucionNormalizador`, which lacks that button. Expose per-execution cancellation on the page users actually see while the full syllabus ETL runs, including Cactus extraction. Request backend cooperative cancellation rather than pretending to kill in-flight downloads or LLM calls.

## Allowed edit surfaces
- `frontend/src/components/InspeccionEjecucionNormalizador.jsx`
- `frontend/src/components/InspeccionEjecucionNormalizador.test.jsx`
- `frontend/src/components/NormalizadorPanel.jsx`
- `frontend/src/components/NormalizadorPanel.test.jsx`

No backend mutation, no personal syllabus/output artifacts, no commit or push without explicit authorization. Preserve all unrelated dirty backend files.

## Tasks
- [x] T1 Added cancel action and explicit HITL active/inactive status to `/{id}` inspector, with tests. Reused existing API helper, confirmation, duplicate guard, persisted pending status, retry on request failure, polling through `extrayendo` to `cancelado`, and per-execution local state. Backend stores `parametros.hitl` as a string, so notice accepts exact `"0"`/`"1"` and 0/1; missing/invalid values produce no false status. Independent Vitest 30/30 and Next build passed; LSP check reported 0 errors but inconclusive coverage (silent-on-clean server). No runtime HTTP cancellation has been verified.
- [ ] T2 Diagnose the user's `/cancelar` 404 end-to-end, reproduce the exact URL/method with a bounded HTTP or integration harness, and fix only the actual broken boundary. Do not POST to or cancel any real active execution. Read-only probes show both backends on 8001/8003 register POST `/normalizador/ejecuciones/{id}/cancelar`; GET of that path returns 405, while direct backend GET `/api/normalizador/.../cancelar` returns 404. Browser's actual URL, port, HTTP method, and response body remain unknown; a Next proxy is not currently listening. Also check for stale in-memory run identity after server restart: report GET reads persisted data, cancel POST requires `_ejecuciones` in this process.
- [x] T4 `/normalizador` remains accessible while a run is active: removed only the mount-time `router.replace` during restoration; kept current-run tracking, input lock, history and its `Inspeccionar` link to the active run. Explicit `router.push` on new run remains. Updated existing restoration test and independently verified 52 combined inspector/normalizer tests, Next build and scoped diff check. On explicit user selection to push only history/navigation, committed exactly the two NormalizadorPanel files as `a12a6e1` (`fix(frontend): keep normalizer history reachable`), pushed without force, and confirmed origin/test/local-llm-technical-pipeline HEAD `a12a6e174129190d8f8e2c2b9a180336f9695e7e`. Inspector button/HITL edits remain uncommitted and unpushed; no runtime browser check.
- [ ] T3 Final verification after resolving 404: re-run focused frontend tests, build/runtime smoke if feasible, inspect scoped diff and report skipped checks. Do not commit or push without a new explicit authorization.

## Findings
- Entry form already renders “Cancelar procesamiento” but `iniciar` routes to `/{id_ejecucion}`.
- Inspector already polls `GET /ejecuciones/{id}/reporte`, but its active-state set omitted `extrayendo` even though backend accepts cancellation in that state. Its report manifest carries `cancelacion_solicitada`.
- Backend cancel is a persisted cooperative request; current in-flight work may finish, and partial audit/CSV artifacts may remain. Do not claim a hard kill or deletion.
- Frontend Next 16 client-component docs confirm state and window confirmation belong in the existing `"use client"` inspector; no new dependency required. 30 inspector tests and Next build pass, but no full-route HTTP cancellation has been verified.
- HITL notice handles exact string/number 0/1 without hiding existing progress, but is still local/unpushed. Confirm actual failing URL before claiming cancellation fixed; do not guess a new `/cancelar` route when POST already exists on backend.
- Native review INSPECT after the navigation commit returned applicability `unrelated`, projecting only remaining dirty workspace files including the uncommitted inspector changes; no review lineage or approval for the pushed commit.
- `/normalizador` formerly called `router.replace('/NOR_...')` on restoration; removing it leaves the already-rendered history accessible. Explicit `router.push` still navigates to the inspector when a new run starts.

## Acceptance
On the active inspection route the HITL mode is plainly visible, a user can request cancellation exactly once, see pending acknowledgement after reload, and see terminal `cancelado` via polling. `/normalizador` remains open while the same run is active, displays the history panel and a path back to the active run, but retains the input lock. A real or representative end-to-end request reaches the correct backend rather than returning 404; no action for terminal executions. Existing running jobs and unrelated work stay untouched.
