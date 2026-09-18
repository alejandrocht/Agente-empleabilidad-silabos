# Immediate technical HITL actions

## Goal

Allow reviewers to add or discard LLM-generated technical competency proposals immediately, materializing the technical CSVs from the same backend decision transaction while preserving package batch review behavior.

## Tasks

- [x] Confirm the technical row decision contract, current revision handling, and backend audit fields.
- [x] Submit technical ADD and DISCARD actions immediately from the proposal card; keep KEEP_PENDING available without inventing data.
- [x] Preserve package-mode batch decisions and add regression coverage for immediate actions and discard reasons.
- [x] Run focused backend/frontend tests, lint/type checks, build, and diff validation.

## Acceptance criteria

- Clicking ADD on a technical proposal submits exactly that proposal with the current queue revision and refreshes the pending queue/CSV state.
- Clicking DISCARD opens a required reason control, submits `DISCARD`, and removes the proposal from the pending queue while retaining an auditable journal entry.
- KEEP_PENDING and legacy/package review behavior remain unchanged.
- No second confirmation request is required after a successful ADD/DISCARD decision.
- Approved technical proposals resolve their referenced source outcomes before quarantine evaluation, so the technical CSV package can become importable even when the syllabus has no declared generic competency.
