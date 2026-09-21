# Technical competency context window

## Goal
Improve the curricular analyst context so the front-selected career guides catalog selection, learning outcomes remain compact literal evidence, and the technical catalog is actually available to the LLM. Prepare an offline benchmark scaffold without requiring benchmark execution now.

## Scope
- Preserve the career supplied by the frontend as the execution input; use the same accent/case/underscore-insensitive key for catalog lookup.
- Include the career-scoped technical catalog candidates in the prompt context.
- Remove outcome metadata that does not help competency inference (`tipo` and `orden`); keep literal outcome text.
- Do not add outcome IDs or `logro_refs` to the model contract.
- Add deterministic tests and a future offline benchmark fixture/runner; do not call a live LLM or external service.

## Non-goals
- Do not touch the concurrent post-HITL fix surfaces.
- Do not change frontend behavior or public CSV schemas.
- Do not introduce embeddings, a vector database, or a live benchmark run in this change.
- Do not treat model output as authoritative; Python grounding/materialization remains the authority.

## Tasks
- [x] Align catalog career lookup with the normalized frontend career while preserving catalog display text.
- [x] Simplify the prompt context and strengthen catalog-guidance instructions without adding outcome references.
- [x] Update focused unit tests for the prompt/context and catalog lookup contract.
- [x] Add an offline benchmark fixture schema, templates, and evaluator scaffold for later labeled cases.
- [x] Run focused tests, static checks, and an integration-shaped prompt smoke test; isolate unrelated concurrent diffs.

## Verification evidence
- Focused pytest: `cd backend && .venv/bin/pytest -q tests/unit/test_analista_tecnico.py tests/unit/test_benchmark_tecnico.py` — 27 passed.
- Ruff: focused analyst/benchmark files — all checks passed.
- Mypy: analyst and benchmark evaluator — no issues found.
- Benchmark template CLI: no cases/no predictions reported; no live service invoked.

## Work-unit commits
- Not applicable; parent owns commits.
