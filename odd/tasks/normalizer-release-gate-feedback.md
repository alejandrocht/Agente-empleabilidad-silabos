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

## Constraints

- Do not change backend gate policy or make deterministic fallback publishable.
- Do not fabricate human-review work when the approval count is zero.
- Keep the patch minimal and reuse existing manifest/release-gate helpers.
- Preserve Spanish UI copy because the existing product UI is Spanish.
- Commit and push to `test/local-llm-technical-pipeline` were explicitly authorized after verification.

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

## Acceptance criteria

- A `TECHNICAL_ANALYSIS_FAILED` run with zero pending approvals does not suggest that the user must resolve human decisions.
- The UI identifies that technical analysis was unavailable/failed and that publication was blocked by the gate.
- The Review tab remains truthfully empty when no decisions exist.
- A payload containing only `checks.approval.pending_count > 0` activates the Review flow.
- Focused tests pass.

## Progress

- Diagnosis confirmed from the live payload supplied by the user.
- Root cause: technical analyst unavailable, deterministic fallback completed, gate intentionally blocked publication.
- NRG-1 completed with observed RED/GREEN evidence.
- NRG-2 completed with explicit technical-blocker feedback, `pending_count` support, and simplified JSX rendering.
- NRG-3 completed through writer verification, an independent verifier, and a parent spot check.
- Source/test work-unit commit: `31a5f2b1edace9bebfbaa728cfef76ed4a8b9079` (`fix(normalizer): explain gate blockers`).
- Push to `test/local-llm-technical-pipeline` was authorized; remote confirmation is reported after delivery.

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
- After the source commit isolated the two-file range, native assess remained unavailable and native inspect stopped on `managed_assets_outdated`; no review lineage was created. Independent verification remains the verification of record.
