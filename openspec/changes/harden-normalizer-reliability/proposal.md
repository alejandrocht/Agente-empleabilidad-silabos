# Proposal: Harden Normalizer Reliability

## Intent

Harden the local normalizer and Neo4j publication workflow against the one confirmed critical finding and seven confirmed high-severity findings recorded in `explore.md`. The change protects administrative routes, prevents unsafe resource allocation, makes execution and import state recoverable, preserves data integrity during concurrent human-in-the-loop (HITL) decisions, and blocks publication when semantic analysis is incomplete.

The deployment contract for this change is a single local instance. Administrative access is protected by a replaceable loopback-only request guard until real user authentication is introduced with the web application.

## Scope

### In scope

1. **Critical — unauthenticated administrative routes**
   - Add one replaceable FastAPI router dependency that accepts only direct loopback peers (`127.0.0.1`, `::1`, and the platform's equivalent loopback forms).
   - Apply it uniformly to `/normalizador/**` and `/neo4j/**`.
   - Do not trust `Host`, `X-Forwarded-For`, or similar headers as authorization.
   - Leave `/health`, `/chat`, `/chat/stream`, `/preguntar`, and dashboard routes unchanged.
   - Document that reverse-proxy and multi-host operation are unsupported until real authentication replaces this guard.

2. **High — finalization removes the Neo4j import source**
   - Preserve or materialize a minimal importer-owned syllabus source artifact during normalizer completion.
   - Keep bulky staging files disposable and keep the preserved source out of public output downloads.
   - Support a compatibility fallback for historical executions where only `limpios/silabos.jsonl` exists.

3. **High — restarted executions become uncancellable zombies**
   - At local single-instance manager initialization, delete persisted non-terminal executions that have no live in-process worker.
   - Preserve terminal history and its readable reports.
   - Do not attempt to resume arbitrary work after restart.
   - Document that multiple workers sharing one data directory are unsupported; startup cleanup must not be presented as safe for that deployment model.

4. **High — HITL snapshot/rollback can undo concurrent success**
   - Capture transactional snapshots only after entering the existing mutation lock and validating the target directory.
   - Keep mutation, rollback, and atomic file writes within the lock's protected critical section.
   - Preserve existing test hook seams and avoid introducing a second lock hierarchy.

5. **High — per-batch LLM failures aggregate as success**
   - Track batch invocation and response failures across the complete curricular analysis.
   - Retain successful and failed audit evidence, but expose an aggregate failure to the cleanup/release gate.
   - Force failed or incomplete semantic analysis to remain non-public and block Neo4j import eligibility.
   - Keep offline mode deterministic and preserve non-fatal human-review handling only where every source logro has valid coverage and no batch invocation failed.

6. **High — Neo4j commits before local history completion**
   - Treat Neo4j graph state and local JSON history as separate durability domains; do not claim cross-system atomicity.
   - Record sufficient local import intent and lineage for deterministic recovery of an `en_progreso` import.
   - Reconcile graph-tagged imports whose graph transaction committed before local completion was durable.
   - Use atomic local history replacement and explicit recovery outcomes; preserve existing pre-commit failure handling.
   - Keep transaction callbacks idempotent because the Neo4j driver may retry them.

7. **High — rollback deletes relationships reused by later imports**
   - Guard relationship deletion with dependency/lineage checks so reverting one import cannot remove an edge required by a later non-reverted import.
   - Support existing scalar `_ciar_import_id` metadata while handling the selected future-compatible ownership representation if introduced by the implementation.
   - Never delete untagged domain relationships or relationships still required by surviving imported nodes/coverage.

8. **High — upload and ZIP limits are enforced too late**
   - Reject oversized uploads with HTTP `413` before creating execution history whenever trustworthy length metadata proves the request is too large.
   - Always enforce the limit while streaming, including when metadata is absent or false.
   - Abort at the byte boundary and remove every partial file and execution directory.
   - Validate ZIP expanded-entry limits without retaining an oversized raw upload.
   - Never load the entire upload into memory.

### Read-only assessment

The curricular analyst system prompt and its structured-output models remain an assessment-only concern. The proposal records the observed strengths, ambiguities, token-cost considerations, and prompt-injection risk from `explore.md`, but does not edit the prompt or include prompt changes in functional implementation. Python-side schema validation, grounding checks, and release-gate blocking remain the enforcement authority.

### Explicit exclusions and non-goals

- The medium frontend polling issue is excluded.
- No changes to frontend polling or other frontend behavior.
- No user, role, bearer-token, or general authentication system in this change.
- No replacement of the FastAPI, LangGraph, normalizer, or Neo4j architecture.
- No attempt to resume in-flight Python workers after process restart.
- No live LLM, Neo4j, LangSmith, browser, paid API, or external production call.
- No public exposure of staging artifacts.
- No prompt edits for the curricular analyst.
- Keep PR #8 unchanged; this is a separate change.

## Affected areas

| Area | Expected changes |
| --- | --- |
| HTTP boundary | `backend/api/servidor.py`, `backend/agente/api/normalizador.py`, `backend/agente/api/neo4j_importacion.py`; replaceable loopback dependency and 413 upload boundary |
| Execution lifecycle | `backend/agente/normalizador/ejecuciones.py`; bounded finalization and startup cleanup of stale non-terminal manifests |
| Syllabus import artifacts | normalizer finalization and `backend/agente/db/neo4j_importador.py`; stable minimal source and compatibility loading |
| Curricular analysis | `backend/agente/normalizador/silabos/analista_llm.py` and cleanup/release-gate integration; aggregate batch failure blocking without prompt changes |
| HITL transactions | `backend/agente/normalizador/silabos/transaccion_aprobaciones.py`; lock-before-snapshot ordering |
| Neo4j lineage and rollback | `backend/agente/db/neo4j_importador.py`; deterministic history reconciliation and guarded relationship deletion |
| Tests and operator documentation | focused backend unit/API tests, fake LLM/Neo4j contracts, and local-only deployment notes |

The exact implementation file set must be confirmed during task planning; no functional source code is changed by this proposal phase.

## Design principles and constraints

- Prefer deep modules with small, replaceable interfaces at the HTTP guard, bounded-copy, execution reconciliation, import lineage, and rollback seams.
- Reuse existing locks, persistence formats, hooks, and terminal-state vocabulary where possible.
- Keep tests with the behavior they verify and use deterministic fakes/contracts only.
- Use atomic local file replacement for history and preserve audit evidence when publication is blocked.
- Treat syllabus and profile text as untrusted data, while recognizing that prompt wording is defense-in-depth only; this change does not alter the prompt.
- Do not use forwarded headers to expand the local-only trust boundary.

## Verification approach

Implementation must follow strict TDD and remain offline:

- FastAPI `TestClient` tests for missing/non-loopback access and unchanged public routes.
- Bounded `BytesIO`/request-stream tests proving early 413 behavior, no retained partial files, and no execution history.
- Finalization/importer fixtures proving the stable syllabus source survives cleanup and supports preview/import loading.
- Temporary-directory manifest tests proving startup removes stale non-terminal executions while preserving terminal history.
- Deterministic fake-hook tests proving lock → snapshot → mutate → rollback ordering and preventing stale concurrent rollback.
- Fake LLM tests where one batch fails and another succeeds, proving aggregate failure blocks publication while retaining evidence.
- Fake Neo4j driver/session/transaction tests for idempotent write behavior, committed-graph/local-history reconciliation, and recovery of interrupted imports.
- Captured Cypher and fake graph scenarios proving rollback preserves relationships shared with later imports and legacy scalar tags remain supported.
- Existing backend lint, typecheck, compile, and focused/full test commands as applicable; no live boundary acceptance.

## Delivery and review forecast

The confirmed delivery strategy is **`auto-chain`** with a **400 changed-line review budget**. The earlier preflight default of `ask-on-risk` is superseded by the user's explicit correction. Chain strategy remains deferred until the task forecast determines the smallest cohesive review slices.

Tasks should be organized by reviewable work unit, with tests included in the same unit. The likely units are:

1. administrative boundary hardening;
2. bounded uploads and execution lifecycle cleanup;
3. stable import source and aggregate LLM failure gating;
4. HITL transaction safety;
5. Neo4j history recovery and relationship-safe rollback.

This list is a planning forecast, not a final chain selection. If the task forecast exceeds 400 authored changed lines, implementation should automatically use cohesive chained review slices rather than compressing code or omitting tests.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Existing local clients/tests call administrative routes anonymously | Add deterministic test configuration and update local operator documentation; keep non-administrative routes unchanged. |
| Loopback protection is mistaken for production authentication | Name the dependency as replaceable, reject forwarded-header trust, and document the single-host limitation. |
| Multipart/framework behavior differs from documentation | Lock behavior with local `TestClient` and bounded-stream tests on the repository's pinned stack. |
| Startup cleanup removes work belonging to another process | Declare shared-data multi-process operation unsupported and limit cleanup semantics to the local single-instance manager contract. |
| Preserving an importer source accidentally exposes staging data | Store only the minimal importer-owned artifact and retain output filtering tests. |
| Partial LLM success is mistaken for complete semantic coverage | Carry an aggregate failure marker into the release gate and keep partial reports non-public. |
| Neo4j and local history diverge after a crash | Persist lineage/intent, inspect tagged graph evidence through deterministic reconciliation, and expose explicit indeterminate outcomes rather than false success. |
| Rollback damages shared graph structure | Require dependency-aware deletion and test shared-edge scenarios for both legacy and new metadata. |
| Review workload grows beyond one PR | Use the confirmed `auto-chain` strategy and defer exact chain structure until tasks are forecast. |

## Rollback

Rollback is by work unit, not by file type:

- Revert the administrative-boundary unit to remove the loopback dependency while leaving unrelated public routes unchanged.
- Revert the upload unit to restore the prior upload path only if the bounded-copy contract causes an unacceptable compatibility failure; this does not restore retained oversized artifacts as a desired behavior.
- Revert startup reconciliation only with an explicit operational decision because already-deleted stale non-terminal manifests cannot be recovered by code rollback.
- Revert the importer artifact, LLM gate, HITL transaction, or Neo4j lineage unit independently using its focused tests and data-format compatibility handling.
- Do not perform destructive schema migration as part of this change; legacy history and scalar relationship metadata must remain readable.

## Success criteria

The change is successful when all of the following are true:

1. Every `/normalizador/**` and `/neo4j/**` route rejects non-loopback peers through one replaceable guard, while health, chat, and dashboard routes retain their current access behavior.
2. An oversized upload receives `413`, creates no execution-history record, and leaves no partial file or directory, regardless of whether request length metadata is present.
3. Finalized syllabus executions retain exactly the minimal importer-required source artifact without making staging data downloadable.
4. Manager initialization removes persisted non-terminal executions without live workers and leaves terminal history intact under the documented single-instance contract.
5. HITL snapshot capture cannot occur outside the mutation lock, and deterministic concurrency/order tests cover failure rollback.
6. Any failed curricular LLM batch prevents publication/import eligibility while preserving successful and failed audit evidence; prompt files remain unchanged.
7. Interrupted Neo4j/local-history transitions have deterministic reconciliation outcomes, atomic local history updates, and no false completion claim.
8. Reverting an earlier import preserves relationships required by later imports and supports legacy scalar ownership metadata.
9. Focused offline tests and applicable repository quality gates pass without live LLM, Neo4j, LangSmith, browser, or paid API calls.
10. The implementation is forecast and sliced according to the 400-line review budget using the confirmed `auto-chain` strategy.

## Authoritative inputs

- `openspec/changes/harden-normalizer-reliability/explore.md`
- `openspec/changes/harden-normalizer-reliability/research.md`
- `openspec/changes/harden-normalizer-reliability/preproposal.md`
- `openspec/config.yaml`
- `openspec/project-context.md`
- `AGENTS.md`
- `CLAUDE.md`
