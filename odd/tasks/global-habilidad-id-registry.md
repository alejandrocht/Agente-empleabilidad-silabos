# Global HAB_TEC identity registry

## Goal
Allow technical skills without an official `COMP_TEC_####` reference to receive a stable, globally unique `HAB_TEC_####` ID only when the shared HITL/automatic approval path approves and materializes them. Pending proposals remain unassigned during initial staging. Reuse an existing ID only when the normalized skill name and description match; otherwise allocate an unused ID. Keep official catalog files unchanged.

## Confirmed constraints
- Existing official `COMP_TEC_####` references continue to resolve to `HAB_TEC_####` IDs.
- The registry is separate from official catalogs, shared across executions/careers, and persists with execution data.
- Identical content shares one ID globally; different content must not collide with official or registered IDs.
- Do not push or modify the official catalog.

## Tasks
- [x] Add a transactional registry backed by a separate SQLite file; seed official content/IDs and allocate collision-free IDs for new content. Evidence: the focused registry suite observed 5 passed.
- [x] Integrate registry resolution through the shared HITL/automatic approval path, preserving pending proposals during initial staging, rollback, and existing CSV contracts. Evidence: the final focused verification passed.
- [x] Verify cross-execution content reuse, document the registry contract, and complete regression and verification checks. Evidence: final focused tests, LSP diagnostics, and `git diff --check` are clean.

## Verification
- Registry complete; integration complete through the shared HITL/automatic approval path; regressions, documentation, and verification complete.
- Strict TDD; runner: `python -m pytest` from `backend`.
- Final focused command from `Agente-empleabilidad-silabos/backend`:
  `uv run --locked python -m pytest tests/unit/test_post_hitl_workflow.py tests/unit/test_registro_habilidades.py tests/unit/test_salida_catalogos.py tests/unit/test_normalizador_silabos.py tests/unit/test_normalizador_api.py tests/unit/test_normalizador_ejecuciones.py -q`
  Observed result: `93 passed in 3.69s`.
- LSP: 0 errors across 5 changed Python paths.
- `git diff --check`: clean.
- Verified that pending proposals remain unassigned during initial staging; approved unmatched proposals emit a `HAB_TEC_####` ID; identical skills reuse the ID across executions; distinct content does not; and existing COMP references preserve their current output IDs.
- No commit, push, or review occurred.

## Boundaries
- No changes to official catalog contents, Neo4j live data, or unrelated dirty files.
- No commit or push without explicit authorization.
