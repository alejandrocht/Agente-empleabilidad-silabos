# Fix technical HITL visibility, proposal coverage, and cancellation

## Goal

Ensure technical LLM proposals are visible for human approval, every syllabus with usable technical learning-outcome evidence yields at least one valid pending technical proposal without inventing unsupported competencies, and cancellation stops the worker between model calls while the UI follows the execution to a terminal state.

## Tasks

- [x] Confirm the technical approval panel is not gated out by technical mode and render the existing `/pendientes` queue for technical proposals.
- [x] Tighten technical proposal materialization so catalog-backed proposals accept literal evidence from the extracted learning outcomes (including the general outcome where valid), while retaining exact catalog references and no fabrication; record a warning/quarantine outcome when a syllabus truly has no usable technical evidence.
- [x] Make cancellation cooperative at the syllabus boundary and keep frontend polling until the backend reports `cancelado`.
- [x] Add regression tests for technical HITL rendering, proposal coverage/materialization, and cancellation lifecycle.
- [x] Run focused backend/frontend tests, lint/type checks applicable to changed files, and `git diff --check`.

## Verification note

Focused backend (52 tests), frontend (82 tests), Ruff, directed mypy, Next.js build, and `git diff --check` pass. The broad backend suite remains a separate blocker: 740 passed and 27 failed in existing approval, embedding, API, generated-query, policy, and output-contract drift areas; unrelated working-tree changes were preserved.

## Acceptance criteria

- A completed technical syllabus execution with pending proposals displays the technical proposals and ADD/KEEP_PENDING controls in the UI.
- A valid proposal is never silently omitted because it references a general learning outcome; Python still owns catalog identity and literal evidence validation.
- No unsupported technical competency is fabricated when no usable learning-outcome evidence exists; the execution records an explicit warning/quarantine outcome.
- Clicking cancel eventually produces terminal `cancelado`; the UI does not stop polling at `cancelacion_solicitada` and no later syllabus model call starts after the cancellation flag is observed.
- Existing legacy curricular approval behavior remains unchanged.
