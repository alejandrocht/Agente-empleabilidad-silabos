# Centralize run-specific progress in the execution inspector

Status: in progress
Branch: test/local-llm-technical-pipeline

## Goal
`/normalizador` is for choosing a new source, starting a run, and browsing history (plus a compact pointer to an active run). `/{NOR_HASH}` is the single authoritative view for all per-execution status: persisted HITL mode, active phase, Cactus extraction counters, LLM cleaning/analysis counters, error/audit status and exactly the syllabus/course marked as processing **now**, not the queue or all future syllabi. Continue to use the existing report manifest and its polling; no new backend endpoint or user-document processing.

## Allowed edit surfaces
- `frontend/src/components/InspeccionEjecucionNormalizador.jsx`
- `frontend/src/components/InspeccionEjecucionNormalizador.test.jsx`
- `frontend/src/components/NormalizadorPanel.jsx`
- `frontend/src/components/NormalizadorPanel.test.jsx`

Respect the existing uncommitted inspector cancellation/HITL changes and unrelated dirty backend. No commit or push without explicit user authorization.

## Tasks
- [x] T1 Inspector now shows per-run source phase/counters, LLM phase/metrics and last bounded event, plus exactly one syllabus marked `procesando` for its actual phase; queued/completed entries are not rendered as the current course. Missing/ambiguous active entries are explicit, and an active entry with no course/filename says the name is unavailable rather than fabricating one. Existing persisted HITL banner and cancellation control remain local. Focused tests: 38 passed; independent check before the final no-name regression was 37 passed with scoped diff check. No live browser/HTTP execution claimed.
- [x] T2 Reduced `/normalizador` to source/start form, compact active-run link and existing history below, removing duplicate run-specific display. Retained HITL for the **next** run, blocked controls while active, no redirect on return and history links. Moved parity to inspector before closing: six mandatory CSVs including skills are previewed/gated, `validado` states continue polling without offering backend-invalid cancellation, the audit tab downloads the consolidated report, and skill counts appear. Approval and Neo4j import were already there. Independent frontend suite: 12 suites/96 tests passed, Next build passed, scoped diff check clean. Net local diff across four frontend files: 996 insertions, 2,994 deletions (including earlier uncommitted inspector cancel/HITL work), with a large but honest deletion of redundant views/tests. No commit/push.
- [x] T3 Independent frontend verification: 12 suites/96 tests passed, Next production build passed, scoped `git diff --check` clean. LSP reported zero diagnostics but was inconclusive (silent-on-clean server), not proof of clean. Isolated `agent-browser` smoke with synthetic GET-intercepted run passed: `/normalizador` shows form, active link, history and no duplicate progress; `/{NOR_HASH}` shows HITL disabled, phase/progress, only the processing course, no queued course and an unclicked cancel action; four GETs returned 200, no POST, browser errors empty. Own QA server/browser cleaned up. The first mock attempt failed because an overbroad blocking rule intercepted GETs; it was discarded and rerun correctly. `git status` confirms only the four frontend files and this task document in this feature scope; branch still at `a12a6e1`. No commit/push per user restriction. Real `/cancelar` 404 remains independently blocked on Network URL/method/response; no real execution or cancel action was tested. Native review assessment was unassessable because the repository contains unrelated untracked files; the independent verifier ran regardless. Review inspect was blocked on intended-untracked selection and showed unrelated tracked changes, so no broad lineage was started or consent inferred. Engram mirror unavailable because the local memory provider could not resolve server identity.

## Findings
- Both `GET /normalizador/ejecuciones/{id}` and `GET .../{id}/reporte` serialize the same live `progreso_fuente`, `progreso_llm` and immutable-per-run `parametros.hitl`; inspector need not invent state from the editable switch.
- `ProgresoLimpiezaLLM.silabos` includes queued and completed entries as well as `estado_extraccion`/`estado_analisis='procesando'`. Rendering the array would violate the request; select the active entry only, and use `curso || archivo` for its label.
- Cactus downloads can run concurrently; its `mensaje` can identify a last-completed course, not an unambiguous current one. Show source phase/counters without presenting that message as the current course.
- The inspector polls every 3 s and now shows counters plus only the current syllabus. `/normalizador` now contains form, compact active link and history; its old duplicate displays were removed locally. Historical build/test coverage needs revalidation after inspector parity fixes.
- The backend current package includes `catalogo_habilidades.csv` as a sixth mandatory CSV, while inspector `CSV_PREVIEW_NAMES_TECNICOS` still lists five, making preview and import-gate validation incomplete. `validado` and `validado_con_advertencias` are intermediate nonterminal states; inspector must keep polling but must not expose cancel there because backend rejects it. The existing consolidated report URL can preserve audit access from the former panel.

## Acceptance
The user can open `/normalizador` during any run to start/view history and follow one active-run link. `/{NOR_HASH}` clearly shows the persisted HITL mode and real-time per-run indicators, including a current cleaning course only when the backend marks that syllabus `procesando`; no full syllabus queue is rendered there. Other running jobs and source docs are unchanged.
