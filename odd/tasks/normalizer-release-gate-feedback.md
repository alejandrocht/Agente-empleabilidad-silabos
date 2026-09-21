# Normalizer release-gate feedback

## Objective

Make the historical normalizer inspection distinguish technical release-gate blockers from pending human review, while honoring every approval-count field emitted by the backend contract.

## Problem

Execution `NOR_4158c802ebd84541` completed deterministic processing but returned `BLOCK_IMPORT` with blocker `TECHNICAL_ANALYSIS_FAILED`, analysis state `FALLBACK_DETERMINISTA`, and finding `ANALISTA_TECNICO_NO_DISPONIBLE`. It had zero pending approvals. The current UI correctly leaves the Review queue empty, but its generic “available for review” copy does not explain the technical blocker. The frontend also ignores `checks.approval.pending_count` when approval summary data is absent.

## Why

Users must be able to tell the difference between a completed-but-technically-blocked run and a run awaiting human decisions. Otherwise a correct empty Review panel looks like missing data or a failed workflow.

## Scope

- `frontend/src/components/InspeccionEjecucionNormalizador.jsx`
- `frontend/src/components/InspeccionEjecucionNormalizador.test.jsx`
- `backend/agente/normalizador/silabos/limpieza.py`
- `backend/tests/unit/test_normalizador_silabos.py`

## Constraints

- Do not change backend gate policy or make deterministic fallback publishable.
- Do not fabricate human-review work when the approval count is zero.
- Keep the patch minimal and reuse existing manifest/release-gate helpers.
- Preserve Spanish UI copy because the existing product UI is Spanish.
- Commit and push to `test/local-llm-technical-pipeline` were explicitly authorized after verification.
- Ollama context size is configured outside the OpenAI-compatible request path; this repository change classifies the resulting failure accurately but does not alter the Ollama runtime setting.

## Execution configuration

- Route: delegated direct writer (`gentle-ai-worker`).
- Trigger: two non-trivial frontend files (component plus regression tests).
- TDD: regression-first RED → GREEN requested for the exact payload shape.
- Focused runner: `cd frontend && npm test -- src/components/InspeccionEjecucionNormalizador.test.jsx`.
- Delivery strategy: `ask-on-risk`; forecast under 120 authored changed lines.
- Engram mirror: pending because the configured Engram provider is unavailable.

## Tasks

- [x] **NRG-1 — Add failing release-gate regression**
  - Model `publicable=false`, `TECHNICAL_ANALYSIS_FAILED`, `FALLBACK_DETERMINISTA`, zero pending approvals, and no outputs.
  - Assert that the UI explains the technical publication blocker without implying pending human review.
  - Assert the Review panel still reports no pending human decisions.
  - Evidence: focused RED produced 2 failures and 10 passes before the component change; focused GREEN produced 12 passes.

- [x] **NRG-2 — Fix gate feedback and approval fallback**
  - Surface a concise, actionable explanation for technical gate blockers in the inspection UI.
  - Read `checks.approval.pending_count` in both pending-count and requires-decision fallbacks.
  - Preserve behavior for genuine pending approval queues.
  - Evidence: independent diff inspection confirmed no backend-policy or publishability change; the added rendering decision uses precomputed state rather than a nested ternary.

- [x] **NRG-3 — Verify focused behavior**
  - Run the focused component test file.
  - Inspect the final diff for unrelated changes and accidental debug output.

- [x] **NRG-4 — Add truncation-classification regression**
  - Reproduce `LengthFinishReasonError` through the public cleanup seam.
  - Assert the warning code identifies a truncated response rather than an unavailable analyst.
  - Preserve the generic unavailable warning for unrelated exceptions.
  - Evidence: focused RED observed the old `ANALISTA_TECNICO_NO_DISPONIBLE`; focused GREEN passed after classification.

- [x] **NRG-5 — Classify truncated analyst output**
  - Map `LengthFinishReasonError` to `ANALISTA_TECNICO_RESPUESTA_TRUNCADA` with accurate Spanish copy.
  - Preserve deterministic fallback, error detail, and release-gate blocking.
  - Keep all non-length failures on `ANALISTA_TECNICO_NO_DISPONIBLE`.

- [x] **NRG-6 — Verify backend behavior**
  - Run the exact focused backend regression.
  - Run the relevant normalizer syllabus unit file when focused behavior is green.
  - Inspect the final diff and preserve unrelated worktree changes.
  - Evidence: focused regression passed 1/1; full syllabus unit file passed 26/26; independent verification and parent spot check found no blockers.

## Acceptance criteria

- A `TECHNICAL_ANALYSIS_FAILED` run with zero pending approvals does not suggest that the user must resolve human decisions.
- The UI identifies that technical analysis was unavailable/failed and that publication was blocked by the gate.
- The Review tab remains truthfully empty when no decisions exist.
- A payload containing only `checks.approval.pending_count > 0` activates the Review flow.
- `LengthFinishReasonError` produces `ANALISTA_TECNICO_RESPUESTA_TRUNCADA`, not `ANALISTA_TECNICO_NO_DISPONIBLE`.
- Generic analyst failures retain `ANALISTA_TECNICO_NO_DISPONIBLE`.
- Deterministic fallback and release-gate blocking remain unchanged.
- Focused tests pass.

## Progress

- Diagnosis confirmed from the live payload supplied by the user.
- Initial payload classified the analyst as unavailable, but the captured exception proved the model responded and its structured output was truncated at the 4095-token context boundary; deterministic fallback completed and the gate intentionally blocked publication.
- NRG-1 completed with observed RED/GREEN evidence.
- NRG-2 completed with explicit technical-blocker feedback, `pending_count` support, and simplified JSX rendering.
- NRG-3 completed through writer verification, an independent verifier, and a parent spot check.
- Source/test work-unit commit: `31a5f2b1edace9bebfbaa728cfef76ed4a8b9079` (`fix(normalizer): explain gate blockers`).
- Frontend commits were pushed to `test/local-llm-technical-pipeline` and remote head was confirmed at `109f2ded2dc2d1eb2e0cf07a5eaa08c8d14f17c0`.
- A live run then exposed `LengthFinishReasonError` at 4095 total tokens; the user authorized a backend classification fix with tests and another push to the same branch.
- NRG-4 and NRG-5 completed through delegated strict TDD; the focused regression passed and the full syllabus unit file reported 26 passing tests.
- NRG-6 completed through an independent verifier and parent spot check against the post-format source.
- Backend source/test work-unit commit: `fa50fc2acb53c8c122802014293eb01454062d76` (`fix(normalizer): classify truncated output`).
- Next step: commit this updated ODD evidence and push both commits selectively to `test/local-llm-technical-pipeline`.

## Verification evidence

- Initial writer RED: 2 failed and 10 passed before the component change.
- Writer GREEN after implementation and cleanup: 12/12 focused tests passed.
- Independent verifier: 12/12 focused tests passed; scoped `git diff --check` passed; no correctness blockers found.
- Parent spot check: 12/12 focused tests passed in 778 ms.
- Scoped final `git diff --check`: passed.
- LSP/auxiliary scan: the newly introduced nested ternary warning was removed; remaining warnings pre-exist in the large component.
- Two parent spot-check attempts failed before execution because npm was invoked from the repository parent without `frontend/package.json`; a delegated incident check confirmed these were invocation errors, not source failures.
- Native risk assessment was unavailable; the required independent verifier therefore ran.
- Before the source commit, native review inspect created no lineage because unrelated workspace changes prevented a bounded candidate.
- After the frontend source commit isolated the two-file range, native assess remained unavailable and native inspect stopped on `managed_assets_outdated`; no review lineage was created. Independent verification remains the verification of record.
- Backend writer RED observed the old unavailable code; GREEN passed the new truncation regression, and the writer's full syllabus unit file passed 26/26.
- Backend independent verifier reran the focused regression (1/1), full unit file (26/26), and scoped `git diff --check`; all passed with no correctness blockers.
- Parent backend spot check reran the focused regression (1/1 in 0.77s); scoped `git diff --check` passed.
- Pi-lens externally reformatted the two backend paths before commit; the parent reread the post-format diff, reran verification against it, and staged only the authorized backend pair.
- Backend native assess remained unavailable and native inspect again stopped on `managed_assets_outdated`; no review lineage was created.
