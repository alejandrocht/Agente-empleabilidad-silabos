# Integrate `test/local-llm-technical-pipeline` into local `main`

## Recovery context

Resume the local integration of `test/local-llm-technical-pipeline` into `main`. The source branch originally pointed to `a89a875`; the local target `main` originally pointed to `953eb6d`. Rebase onto fetched `origin/main` at `810e862` completed with 39 commits. The first conflict-resolution commit generated during the rebase was `5382747`.

User changes were safely stashed as `pre-test-main-integration-20260924`. The untracked `.codegraph/` directory remained in the worktree. Preserve both; do not discard or overwrite user data. The user authorized correcting backend failures before the local merge. Do not push.

## Progress

- [x] Preserve user changes and fetch the integration base. User changes are stashed under `pre-test-main-integration-20260924`; `.codegraph/` remained untracked; `origin/main` was fetched at `810e862`.
- [x] Rebase the source branch onto fetched `origin/main`. The 39-commit rebase completed; first conflict-resolution commit generated: `5382747`.
- [x] Remove the obsolete LangSmith test and fix whitespace. The corrective changes and focused checks were verified; the full backend run completed with one LangSmith warning.
- [x] Resolve the entity-resolver failures inherited from `origin/main`; the corrective group is complete, and the final full backend suite passed.
- [x] Fix the importer CSV failures involving `id_cob_curricular`.
- [x] Correct the HITL test expectations: two stale assertions expected 404, but draft download actually returns 200. Public outputs remain gated.
- [x] Fix the generated-query streaming assertion failure.
- [x] Fix the API persistence/timing failure.
- [x] Verify the corrective changes. Final backend: 559 passed, 1 LangSmith warning, after the final gate-consistency fix. Frontend: 97 tests and build passed in the previous verification, before that last backend-only fix. Changed Python files passed scoped Ruff, and the working diff passed `git diff --check`. Full Ruff still reports four baseline issues; mypy aborted because of a duplicate module. A live Neo4j query was explicitly declined by the user.
- [x] Record the four observed local corrective commits: `25df57e fix(entity): align resolver with static ontology`; `9d09e11 fix(normalizer): map public coverage IDs for import`; `87e6a31 fix(normalizer): reconcile live and approved states`; `9b0b691 test: retire obsolete analyzer assertions`.
- [ ] Merge locally and restore the user stash. Keep this pending. Do not push. Preserve stash `pre-test-main-integration-20260924` and the untracked `.codegraph/` directory.

## Validation commands

- Backend: `backend/.venv/bin/python -m pytest -q`
- Frontend tests: `npm test` (from `frontend/`)
- Frontend build: `npm run build` (from `frontend/`)
- Run the applicable diff checks before local merge.

Observed corrective verification evidence: `backend/.venv/bin/python -m pytest -q` — 559 passed, with 1 LangSmith warning, after the final gate-consistency fix. `npm test` (from `frontend/`) — 97 tests passed in the previous verification, before the last backend-only fix. `npm run build` (from `frontend/`) — passed in that same previous verification. Scoped Ruff on changed Python files passed; full Ruff still has four baseline issues. Mypy aborted due to a duplicate module. `git diff --check` passed on the working diff. These are prior working-tree results; no verification has been run on the branch after commit `9b0b691`. The user explicitly declined a live Neo4j query. Native review of the uncommitted correction candidate was declined; a separate verifier was used instead. This is verification evidence, not an approved native review.

## Workflow notes

Strict TDD was not activated for this recovery task. The four listed corrective commits are observed. Local merge and stash restoration remain pending; do not push or invent a merge SHA. The user stash label `pre-test-main-integration-20260924` and untracked `.codegraph/` directory remain preserved. Native review was declined for the uncommitted correction candidate; the separate verifier's result must not be represented as native review approval. The user explicitly declined a live Neo4j query. Engram task mirror was unavailable; this file is the recovery record.
