# Guarantee one technical proposal per syllabus

## Goal

Ensure every syllabus with usable learning-outcome evidence produces at least one reviewable technical competency proposal, and preserve proposed technical names through package projections.

## Tasks

- [x] Reproduce zero-proposal output with a deterministic analyzer test.
- [x] Add a minimal evidence-backed fallback when the LLM response is empty or invalid.
- [x] Reproduce and fix technical proposal name loss in package projections.
- [x] Run focused tests, lint/type checks, and report broader-suite boundaries.

## Acceptance criteria

- A syllabus with at least one usable learning outcome yields at least one pending technical proposal after valid and retry responses produce no materializable proposal.
- A syllabus without usable learning outcomes records an auditable warning and does not fabricate a proposal.
- Proposed technical names and descriptions remain visible in package/API projections instead of falling back to `Pendiente de catalogación`.
- Catalog references, IDs, literal evidence, and approval gates remain Python-owned; fallback proposals remain pending human review.

## Verification

- Backend focused regression: `33 passed` across analyzer, package projection, and resilience tests.
- Backend Ruff and strict Mypy: passed for the touched production and test files.
- Frontend focused regression: `19 passed` in `CurricularApprovalPanel.test.jsx`.
- Frontend build and TypeScript check: passed.
- `git diff --check`: passed.
- Full backend suite remains outside this change boundary; known legacy failures are tracked separately.
