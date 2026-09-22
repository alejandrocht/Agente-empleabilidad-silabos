# One-click technical discard

## Goal
Make technical proposal rejection an explicit one-click action. Clicking `Descartar propuesta` must submit `DISCARD` immediately without asking for a reason.

## Scope
- Remove the discard reason dialog, textarea, and confirmation step from the frontend.
- Allow backend `DISCARD` requests without `reason`; preserve supplied reasons for backward compatibility and keep the decision journal intact.
- Leave `ADD`, `KEEP_PENDING`, strict proposal validation, and technical deduplication unchanged.

## Tasks
- [x] Add backend and frontend regressions for one-click discard without `reason`.
- [x] Implement the frontend and backend behavior.
- [x] Run focused backend/frontend checks and inspect the selective diff.
- [x] Record the work-unit commit after verification.

## Verification evidence
- Backend focused suite: `19 passed` (`test_normalizador_ejecuciones.py` and `test_post_hitl_workflow.py`).
- Frontend focused suite: `4 passed` (`CurricularApprovalPanel.test.jsx`).
- Direct API smoke test: `DISCARD` without `reason` returned HTTP 200 and `discarded=1`.
- `git diff --check`: passed.
- Work-unit commit: `daa4c07` (`fix: streamline technical proposal decisions`).
- `gentle-ai-verify` fallback was unavailable because the local extension registry has a duplicate `ask_user_question`; verification ran directly after that failed delegation.

## Constraints
- Do not modify the technical deduplication implementation or its tests.
- Preserve unrelated working-tree changes; stage only files for this feature when committing.
