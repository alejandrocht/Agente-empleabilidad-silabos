# Technical post-HITL workflow repair

## Objective

Make the technical syllabus workflow coherent after the final human decision: the execution manifest, release gate, five canonical CSV outputs, frontend inspection page, and Neo4j validation must agree.

## Problem

The current remote branch materializes and serves five CSVs after approval, but can leave the manifest in `no_publicado`, keep the frontend on an empty Review tab, report stale CSV row counts, and expose a Neo4j action that the backend rejects with HTTP 409.

## Scope

- Reconcile the post-HITL technical execution state and output metadata.
- Make the canonical inspection page refresh decisions and select CSV when the gate is allowed.
- Add API/frontend regression coverage for decision -> materialization -> outputs -> Neo4j validation.
- Preserve existing blocked-gate behavior and all unrelated working-tree changes.
- Do not push, alter LLM prompts/providers, or require Ollama/Neo4j for offline tests.

## Existing changes intentionally outside scope

- `backend/agente/grafo/constructor.py`
- `backend/agente/nodos/prompt_injection.py`
- `backend/agente/utils/logger.py`
- local deletion of `backend/tests/unit/test_langsmith.py` (retained as an existing workspace change)

## Tasks

- [x] Add failing regression coverage at the API and frontend seams.
- [x] Fix atomic post-HITL state, gate, and CSV metadata reconciliation.
- [x] Fix frontend decision refresh and automatic CSV navigation.
- [x] Run focused and full verification; record unavailable external services and pre-existing failures.

## Acceptance criteria

- A final technical `ADD` decision returns `ALLOW_IMPORT`, a publishable terminal state, five canonical CSV outputs, accurate row counts, and successful output downloads.
- A blocked or pending execution exposes no canonical CSV outputs and keeps Neo4j validation blocked.
- The canonical frontend inspection page does not remain on an empty Review panel after all decisions resolve and selects CSV when canonical outputs are ready.
- Backend and frontend regression tests cover the complete offline flow.

## Routing and evidence

- Route: delegated direct writer (`gentle-ai-worker`) because the change spans multiple non-trivial backend/frontend files.
- TDD: strict red -> green -> refactor; worker observed stale-state/Review-tab red cases and then green regression suites.
- Verification: parent reran focused tests and repository checks after the writer returned.
- Delivery: changes remain uncommitted and unpushed under the user’s local-preservation constraint; commit/push stays a separate user decision.
- Memory mirror: pending because Engram is unavailable at the configured local endpoint.

## Progress

- Feature document created before source edits.
- Current remote baseline: `89237b5033105624df63adbdbe683026692a3df1`.
- Regression coverage added for final ADD, manifest/API state, five CSV downloads, offline Neo4j validation, blocked gate protection, stale active metadata, and frontend CSV navigation.
- Backend fix persists terminal state, gate, canonical outputs, hashes, byte sizes, and row counts; active snapshots reconcile metadata and canonical ordering.
- Frontend fix trusts the resolved approval summary over stale proposal rows and automatically selects CSV when previews are ready.
- Focused checks: backend 35 passed / 1 pre-existing timing failure, frontend inspection 10 passed, Ruff passed. Full backend: 489 passed / 2 pre-existing failures; frontend check 69 passed and production build passed; compileall and mypy passed with zero errors.
- The two unrelated full-suite failures are the timing-sensitive `test_inicia_y_consulta_ejecucion_de_silabos` and `test_build_generated_runnable_uses_role_specific_structured_output` expecting an older call signature.
- LSP diagnostics introduced no current-turn errors; existing warnings/typo findings remain outside scope.
- External Ollama and Neo4j services remain intentionally unrequired/unavailable for offline verification.
