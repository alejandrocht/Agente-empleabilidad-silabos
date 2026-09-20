# Fix technical CSV output publication

## Goal

Expose the five materialized technical CSV files after the final HITL decision, even while the execution remains in the in-memory manager snapshot.

## Constraints

- Preserve unrelated tracked and untracked changes.
- Do not require Ollama or Neo4j.
- Do not commit or push.
- Keep the existing release-gate protection: blocked runs must expose no canonical CSV outputs.

## Tasks

- [x] Reproduce the empty `outputs` response with a focused backend regression test.
- [x] Reconcile approved technical CSV metadata at the persisted execution boundary.
- [x] Run focused backend/frontend verification and inspect the final diff.
