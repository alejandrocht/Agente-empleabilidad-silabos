# Pre-proposal decisions — harden-normalizer-reliability

## Status

- Exploration: complete (`explore.md`)
- Research: complete (`documentation` + `open-web`; see `research.md`)
- Product decisions: confirmed
- Proposal ready: yes

## Confirmed scope

- Fix the one critical and seven high-severity findings documented in `explore.md`.
- Exclude the medium frontend polling issue.
- Keep PR #8 unchanged; this is a separate change.
- Use deterministic offline tests and fakes only. Do not call live LLM, Neo4j, LangSmith, browser, or paid APIs.
- Delivery strategy: `auto-chain`; review budget: 400 changed lines; chain strategy deferred until tasks forecast.
- Assess the curricular analyst system prompt read-only; prompt edits are outside the confirmed implementation scope.

## Pending decisions

### D1 — Research selection

Confirmed: run both official-documentation and open-web research before proposal. The research artifact must record exact tool calls, sources, publisher/version context, retrieval time, excerpts, and claim-to-source mappings.

### D2 — Administrative boundary

Confirmed: the current deployment is local-only and user authentication will be introduced later with the web application. For this change, enforce a replaceable loopback-only dependency on `/normalizador/**` and `/neo4j/**`; keep health/chat/dashboard routes unchanged. Do not build a user or bearer-token system now. Tests must prove non-loopback requests are rejected. This resolves the current exposure only under the documented single-host deployment contract.

### D3 — Oversized upload behavior

Confirmed: return HTTP `413` without execution history. Reject from trustworthy length metadata when available; always enforce a streaming byte limit, abort at the boundary, and remove any partial file/directory.

### D4 — Restarted in-flight execution semantics

Confirmed: delete persisted non-terminal executions that have no live worker when the local single-instance manager initializes. Preserve terminal history. Document that multi-process workers sharing one data directory are unsupported; do not delete another live process's work under a claimed multi-process configuration.

## Technical defaults not requiring product choice

- Move HITL snapshot capture under the existing mutation lock.
- Preserve a minimal importer-owned syllabus source artifact rather than all staging data.
- Block publication/import when any LLM batch invocation fails while retaining partial audit evidence.
- Add deterministic Neo4j import-history reconciliation and guarded relationship deletion compatible with legacy scalar ownership metadata.

## Readiness rule

Proposal is ready: selected research is complete and D1–D4 are confirmed without unresolved contradictions.
