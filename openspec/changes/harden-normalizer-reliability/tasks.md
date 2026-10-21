# Tasks: Harden Normalizer Reliability

## Scope and delivery contract

This task plan is for the nested repository `Agente-empleabilidad-silabos/` only. It implements the approved proposal, specification, design, and research findings without changing functional source during this planning phase.

- Strict TDD is mandatory: each unit proceeds RED → GREEN → TRIANGULATE → REFACTOR.
- Each RED → GREEN cycle tests one public behavior seam; tests stay with the production behavior they verify.
- All verification is offline and deterministic. Use fakes, temporary directories, `TestClient`, captured Cypher, and bounded byte streams only.
- Do not call live LLM, Neo4j, LangSmith, Cactus/browser, paid API, or external production services.
- Preserve existing public route paths, response compatibility, manifest/history readability, and additive data formats.
- The curricular analyst system prompt is read-only and is not an allowed edit surface.
- The medium frontend polling issue is excluded; no frontend path is an allowed edit surface.
- During apply, update this file's task checkboxes and evidence notes after each phase; do not edit proposal, spec, design, or research artifacts as implementation substitutes.

## Review Workload Forecast

| Field | Value |
| ------- | ------- |
| Estimated changed lines | 885–1,205 authored lines total; see per-unit estimates below |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Candidate PR 1: U1 → Candidate PR 2: U2–U4 → Candidate PR 3: U5–U6 → Candidate PR 4: U7 → Candidate PR 5: U8 |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

## Canonical implementation checklist

- [x] U1 — Protect administrative routes with one direct-loopback seam. Implement and verify the behavior. <!-- sdd-owner: implementation -->

> Budget-split follow-up: U1 behavior remains complete; its documentation hunks are deferred to the later U2–U4 lifecycle/docs review slice and are not currently landed.

- [ ] U2 — Reject oversized uploads before history allocation and during bounded streaming. Implement and verify the behavior. <!-- sdd-owner: implementation -->

> **U2a sub-slice evidence (early trustworthy `Content-Length` only):** RED added parametrized API coverage for both upload routes and failed with `AssertionError: crear no debe ejecutarse antes del rechazo` after the existing handlers allocated execution history. GREEN added a route seam that returns generic HTTP 413 before FastAPI body parsing and before `gestor_ejecuciones.crear`; the two new cases passed. Final focused API suite: `16 passed`. Targeted Ruff for `agente/api/normalizador.py` and `tests/unit/test_normalizador_api.py`, compileall, and path-scoped diff-check passed. U2 remains intentionally unchecked; bounded streaming, scratch cleanup, ZIP checks, docs/config, and later U2-U8 work are excluded from this sub-slice.

- [ ] U3 — Reconcile stale non-terminal executions at single-instance startup. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U4 — Preserve one private stable syllabus source through finalization. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U5 — Make HITL snapshot, mutation, and rollback one locked transaction. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U6 — Aggregate curricular LLM failures into an explicit publication blocker. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U7 — Reconcile Neo4j graph commits with durable local import history. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U8 — Make relationship rollback ownership- and dependency-safe. Implement and verify the behavior. <!-- sdd-owner: implementation -->

The forecast is high because the eight capabilities cross HTTP admission, execution persistence, importer artifacts, semantic release gating, transactional HITL mutation, local durability, graph lineage, rollback Cypher, focused tests, and operator documentation. The candidate groups are dependency ordered and each remains independently verifiable and rollbackable; the exact chain topology remains deferred as requested.

## Global implementation and verification rules

- Use the active backend package under `backend/agente`; do not restore `backend/src/agente`.
- Use the exact repository commands listed in each unit. A focused command must fail in RED for the intended reason before production changes and pass in GREEN.
- Record the exact RED failure, GREEN result, TRIANGULATE result, and REFACTOR result in the unit's commit/PR evidence and in this file's progress notes.
- Include tests and documentation changes in the same work unit as the behavior they describe.
- Roll back by work unit, not by file type; each unit below names the removable behavior and its boundaries.
- Keep generated fixtures small and authored; do not count generated or oversized fixture output as a reason to omit tests.

## Dependency-ordered vertical work units

### U1 — Protect administrative routes with one direct-loopback seam

**Capability covered:** Replaceable loopback-only access for every `/normalizador/**` and `/neo4j/**` route, while health, chat, and dashboard routes retain their current behavior.

**Depends on:** None. This is the first exposure-reduction slice.

**Exact allowed edit surfaces:**

- `backend/api/servidor.py`
- `backend/agente/api/acceso_administrativo.py` (new)
- `backend/tests/unit/test_normalizador_api.py`
- `backend/tests/unit/test_neo4j_importacion_api.py`
- `backend/tests/unit/test_normalizador_ejecuciones.py`
- `backend/tests/unit/test_normalizador_aprobaciones.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At the FastAPI router-inclusion seam, add tests for direct loopback allow, non-loopback rejection before handler execution, missing/malformed peer rejection, and forwarded-header non-override using explicit `TestClient` peers in `backend/tests/unit/test_normalizador_api.py` and `backend/tests/unit/test_neo4j_importacion_api.py`; run the focused command and record the failing assertions. <!-- sdd-owner: implementation -->
- GREEN: Add the replaceable direct-peer guard in `backend/agente/api/acceso_administrativo.py` using `ipaddress`, and attach one dependency to the two admin routers in `backend/api/servidor.py` without reading authorization headers or changing public routes; rerun the same focused command and record the exact passing result. <!-- sdd-owner: implementation -->
- TRIANGULATE: Extend `backend/tests/unit/test_normalizador_ejecuciones.py` and `backend/tests/unit/test_normalizador_aprobaciones.py` to use explicit loopback peers for administrative calls, and add non-loopback assertions for `/health`, conversation, and dashboard paths; run the exact command below and confirm no external boundary is invoked. <!-- sdd-owner: implementation -->
- REFACTOR: Update `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md` with the loopback-only, no-forwarded-header, single-host limitation and replacement point; rerun the focused tests and `cd backend && python -m ruff check agente/api/servidor.py agente/api/acceso_administrativo.py api/servidor.py`, recording evidence without changing route payloads. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_normalizador_api.py tests/unit/test_neo4j_importacion_api.py tests/unit/test_normalizador_ejecuciones.py tests/unit/test_normalizador_aprobaciones.py
cd backend && python -m ruff check agente/api/servidor.py agente/api/acceso_administrativo.py api/servidor.py
```

**Authored-line forecast:** 90–120 lines.

**Finish state:** Every administrative route is guarded by the one replaceable seam; unchanged public routes remain testable from a non-loopback peer; documentation clearly rejects proxy/multi-host assumptions.

**Rollback boundary:** Revert only the guard module, router dependency wiring, its focused tests, and the associated operator text; do not revert unrelated normalizer or importer behavior.

### U2 — Reject oversized uploads before history allocation and during bounded streaming

**Capability covered:** Raw upload and ZIP expanded limits return `413`, stop at the byte boundary, retain no partial file/history/directory, and preserve accepted uploads without unbounded reads.

**Depends on:** U1 for the protected HTTP surface.

**Exact allowed edit surfaces:**

- `backend/agente/api/normalizador.py`
- `backend/agente/normalizador/silabos/entrada.py`
- `backend/tests/unit/test_normalizador_api.py`
- `backend/tests/unit/test_normalizador_silabos.py`
- `backend/.env.example`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At the upload endpoint seam in `backend/tests/unit/test_normalizador_api.py`, add tiny bounded-stream tests for trustworthy oversized length, absent/lying metadata, exact boundary, cleanup after copy failure, and valid `202` admission; run the focused command and record the current late-allocation/response failures. <!-- sdd-owner: implementation -->
- GREEN: Configure the locked Starlette request-body limit at the normalizer router seam and implement one bounded scratch-file admission helper in `backend/agente/api/normalizador.py`; create execution history only after raw admission and remove scratch/execution artifacts on every rejection or promotion failure; rerun the focused API tests. <!-- sdd-owner: implementation -->
- RED: At the pure ZIP metadata seam in `backend/tests/unit/test_normalizador_silabos.py`, add small `ZipInfo` fixtures crossing entry-count, per-entry, and expanded-total limits without extracting files; run the exact focused command and record the failing cases. <!-- sdd-owner: implementation -->
- GREEN: Extract reusable ZIP limit scanning and limit classification in `backend/agente/normalizador/silabos/entrada.py`, invoke it on the private scratch archive before `gestor_ejecuciones.crear`, preserve existing malformed/semantic validation behavior, and rerun the focused tests. <!-- sdd-owner: implementation -->
- TRIANGULATE: Verify both upload routes, no `NOR_*` directory, no `entrada/` artifact, no scratch residue, bounded reads, and valid acceptance using `backend/tests/unit/test_normalizador_api.py` and `backend/tests/unit/test_normalizador_silabos.py`; run the exact command below. <!-- sdd-owner: implementation -->
- REFACTOR: Document request-body accounting including multipart framing in `backend/.env.example`, `backend/README.md`, and `docs/DOCUMENTACION_TECNICA_CIAR.md`; rerun focused tests and the targeted lint command, preserving the existing `202` success payload. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_normalizador_api.py tests/unit/test_normalizador_silabos.py
cd backend && python -m ruff check agente/api/normalizador.py agente/normalizador/silabos/entrada.py
```

**Authored-line forecast:** 110–150 lines.

**Finish state:** Proven oversized requests fail with `413` before history when possible and during bounded streaming otherwise; ZIP limits are checked privately; accepted requests retain their public contract.

**Rollback boundary:** Revert only bounded admission, ZIP preflight, related tests, and ingress documentation; never restore deliberate retention of oversized artifacts.

### U3 — Reconcile stale non-terminal executions at single-instance startup

**Capability covered:** Startup removes persisted non-terminal manifests without live in-process workers, preserves terminal history/reports, never resumes arbitrary work, and documents the unsupported multi-process data-directory model.

**Depends on:** U2 because upload allocation and lifecycle state must share the same cleanup contract.

**Exact allowed edit surfaces:**

- `backend/agente/normalizador/ejecuciones.py`
- `backend/agente/normalizador/persistencia_ejecuciones.py`
- `backend/tests/unit/test_normalizador_ejecuciones.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At `GestorEjecuciones` initialization, create temporary terminal, recognized non-terminal, malformed, symlinked, and inaccessible manifest fixtures in `backend/tests/unit/test_normalizador_ejecuciones.py`; assert the current manager leaves stale work and record the focused RED failure. <!-- sdd-owner: implementation -->
- GREEN: Add a best-effort repository scan/delete method in `backend/agente/normalizador/persistencia_ejecuciones.py` and invoke it immediately after repository construction in `backend/agente/normalizador/ejecuciones.py`; delete only direct, parseable, recognized non-terminal `NOR_*` directories and do not submit workers. <!-- sdd-owner: implementation -->
- TRIANGULATE: Prove terminal reports remain readable, stale executions are absent from list/get/cancel paths, malformed/symlinked entries do not block startup, and no restart-resume worker is created using only temporary filesystem fixtures; run the exact command below. <!-- sdd-owner: implementation -->
- REFACTOR: Record the single-instance and unsupported shared-data-directory contract in `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`, then rerun focused tests and lint for the two changed modules. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_normalizador_ejecuciones.py
cd backend && python -m ruff check agente/normalizador/ejecuciones.py agente/normalizador/persistencia_ejecuciones.py
```

**Authored-line forecast:** 65–90 lines.

**Finish state:** New local managers clean only valid stale non-terminal executions, preserve all terminal history, and make no multi-process safety claim.

**Rollback boundary:** Revert startup reconciliation and its tests/docs independently; acknowledge that code rollback cannot restore directories already deleted by a prior startup.

### U4 — Preserve one private stable syllabus source through finalization

**Capability covered:** Finalized syllabus executions retain one importer-owned source, preview/import use it after staging purge, public output downloads hide it, and historical `limpios/silabos.jsonl` remains a fallback.

**Depends on:** U3 for lifecycle finalization and U1/U2 for the protected normalizer/import HTTP surfaces.

**Exact allowed edit surfaces:**

- `backend/agente/normalizador/ejecuciones.py`
- `backend/agente/normalizador/silabos/fuente_importacion.py` (new)
- `backend/agente/db/neo4j_importador.py`
- `backend/agente/api/normalizador.py`
- `backend/tests/unit/test_normalizador_ejecuciones.py`
- `backend/tests/unit/test_neo4j_importador.py`
- `backend/tests/unit/test_normalizador_api.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At the finalization/import-source seam, add temporary execution fixtures in `backend/tests/unit/test_normalizador_ejecuciones.py` and `backend/tests/unit/test_neo4j_importador.py` proving the current purge removes the only source and that missing-source importability is unsafe; run the focused command and record the failure. <!-- sdd-owner: implementation -->
- GREEN: Add `RUTA_FUENTE_IMPORTACION`, atomic materialization, and validated stable/legacy resolution in `backend/agente/normalizador/silabos/fuente_importacion.py`; call materialization before purge in `backend/agente/normalizador/ejecuciones.py` and load the resolved source in `backend/agente/db/neo4j_importador.py`. <!-- sdd-owner: implementation -->
- RED: At the public-output seam in `backend/tests/unit/test_normalizador_api.py`, add a fixture that declares the private source in a malformed/historical manifest and assert it is not downloadable; run the focused command and record the RED result. <!-- sdd-owner: implementation -->
- GREEN: Deny the private stable path independently in `backend/agente/api/normalizador.py` while retaining existing allowlists and legacy compatibility; rerun focused API/import/lifecycle tests. <!-- sdd-owner: implementation -->
- TRIANGULATE: Verify idempotent re-finalization, valid source replacement, missing/invalid source blocking, legacy fallback, cleaned staging, digest-label compatibility, and output privacy without Neo4j; run the exact command below. <!-- sdd-owner: implementation -->
- REFACTOR: Document private artifact retention, staging disposal, legacy fallback, and importability rules in `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`; rerun focused tests and targeted lint. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_normalizador_ejecuciones.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_api.py
cd backend && python -m ruff check agente/normalizador/ejecuciones.py agente/normalizador/silabos/fuente_importacion.py agente/db/neo4j_importador.py agente/api/normalizador.py
```

**Authored-line forecast:** 95–130 lines.

**Finish state:** Only the minimal private source survives normal cleanup; importer preview/import can resolve stable or historical source; no public output route exposes it.

**Rollback boundary:** Revert stable-source materialization/resolution and privacy denial independently from stale-execution cleanup; retain compatibility readers for historical source layouts during rollback.

### U5 — Make HITL snapshot, mutation, and rollback one locked transaction

**Capability covered:** Validate first, acquire the existing lock, snapshot, mutate, atomically write, and roll back only the locked operation without undoing concurrent success.

**Depends on:** U3 for the execution directory lifecycle and persisted manifest contract.

**Exact allowed edit surfaces:**

- `backend/agente/normalizador/silabos/transaccion_aprobaciones.py`
- `backend/tests/unit/test_normalizador_aprobaciones.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At the public transaction façade in `backend/tests/unit/test_normalizador_aprobaciones.py`, add recording-hook tests for validate → lock → snapshot → mutation and a non-reentrant lock test that exposes the current pre-lock snapshot/nested-acquisition behavior; run the focused command and record the failure. <!-- sdd-owner: implementation -->
- GREEN: Move root discovery/snapshot into one lock-owned operation in `backend/agente/normalizador/silabos/transaccion_aprobaciones.py`; preserve hook names and façade signatures, keep all writes/rollback under `_LOCK`, and avoid reacquiring it through the compatibility entry point. <!-- sdd-owner: implementation -->
- TRIANGULATE: Exercise success, mutation failure, snapshot failure, restoration failure, and deterministic overlapping-attempt ordering with fake hooks and temporary trees; run the exact command below and verify atomic write hooks remain inside the critical section. <!-- sdd-owner: implementation -->
- REFACTOR: Update the HITL transaction/rollback operator explanation in `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`, then rerun focused tests and targeted lint without introducing a second lock hierarchy. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_normalizador_aprobaciones.py
cd backend && python -m ruff check agente/normalizador/silabos/transaccion_aprobaciones.py
```

**Authored-line forecast:** 70–95 lines.

**Finish state:** The public decision operation has one lock owner, captures snapshots only after validation and lock entry, and cannot restore state observed before a successful concurrent mutation.

**Rollback boundary:** Revert only transaction ordering and its fake-hook tests/docs; preserve unrelated approval policy, catalog, and release-gate behavior.

### U6 — Aggregate curricular LLM failures into an explicit publication blocker

**Capability covered:** Any failed invocation, unusable response, failed retry, grounding failure, or incomplete source coverage remains auditable but blocks public completion and Neo4j import eligibility; valid human review remains non-fatal only with complete coverage and no batch failure.

**Depends on:** U4 for stable import-source eligibility and U5 only for sequencing of independent normalizer correctness work; no prompt edit is permitted.

**Exact allowed edit surfaces:**

- `backend/agente/normalizador/modelos.py`
- `backend/agente/normalizador/silabos/analista_llm.py`
- `backend/agente/normalizador/silabos/limpieza.py`
- `backend/agente/normalizador/silabos/release_gate.py`
- `backend/tests/unit/test_normalizador_analista_llm.py`
- `backend/tests/unit/test_normalizador_silabos.py`
- `backend/tests/unit/test_normalizador_policy.py`
- `backend/tests/unit/test_normalizador_salida_contract.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At `analizar_registros_curriculares` in `backend/tests/unit/test_normalizador_analista_llm.py`, add deterministic fake-LLM cases for one failed batch plus one successful batch, invalid response, repaired omitted IDs, permanently incomplete coverage, retained audit evidence, and final error progress; run the focused command and record current false-success failures. <!-- sdd-owner: implementation -->
- GREEN: Add only additive result fields in `backend/agente/normalizador/modelos.py`, track invocation/response/coverage failures in `backend/agente/normalizador/silabos/analista_llm.py`, and publish `fase="error"`/`reporte_final="error"` only for aggregate failure while continuing later batches. <!-- sdd-owner: implementation -->
- RED: At the release-gate seam in `backend/tests/unit/test_normalizador_silabos.py`, `backend/tests/unit/test_normalizador_policy.py`, and `backend/tests/unit/test_normalizador_salida_contract.py`, add tests requiring `LLM_SEMANTIC_ANALYSIS_INCOMPLETE`, `checks["semantic_analysis"].ok == false`, `BLOCK_IMPORT`, `no_publicado`, retained reports, and unchanged successful human-review policy; run the focused command and record the RED result. <!-- sdd-owner: implementation -->
- GREEN: Implement a pure copied-gate merger in `backend/agente/normalizador/silabos/release_gate.py` and apply it in `backend/agente/normalizador/silabos/limpieza.py`, serializing additive audit fields and preserving partial JSONL evidence without changing the analyst prompt. <!-- sdd-owner: implementation -->
- TRIANGULATE: Run all fake-LLM paths with `NORMALIZADOR_CURRICULAR_LLM=false` controls or injected fakes only; prove failed analysis cannot become public/importable and repaired retry remains non-failing; run the exact command below. <!-- sdd-owner: implementation -->
- REFACTOR: Document semantic failure, audit retention, release blocking, and offline fake policy in `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`; rerun focused tests, targeted lint, and type checks for the allowed production modules. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_normalizador_analista_llm.py tests/unit/test_normalizador_silabos.py tests/unit/test_normalizador_policy.py tests/unit/test_normalizador_salida_contract.py
cd backend && python -m ruff check agente/normalizador/modelos.py agente/normalizador/silabos/analista_llm.py agente/normalizador/silabos/limpieza.py agente/normalizador/silabos/release_gate.py
cd backend && python -m mypy agente/normalizador/modelos.py agente/normalizador/silabos/analista_llm.py agente/normalizador/silabos/limpieza.py agente/normalizador/silabos/release_gate.py
```

**Authored-line forecast:** 120–160 lines.

**Finish state:** Partial semantic analysis remains auditable but is terminal non-publicable and blocked at the release/import gate; prompt source and public CSV schemas remain unchanged.

**Rollback boundary:** Revert aggregate failure fields/gate merger and associated tests/docs as one semantic unit; additive report readers may continue accepting the fields.

### U7 — Reconcile Neo4j graph commits with durable local import history

**Capability covered:** Separate graph/local durability domains, durable import intent, atomic local history replacement, graph marker reconciliation, explicit recovery/indeterminate outcomes, preserved pre-commit failures, and retry-idempotent transaction callbacks.

**Depends on:** U4 stable source resolution and U6 semantic release blocking before importer acceptance; U1 protects the HTTP publication routes.

**Exact allowed edit surfaces:**

- `backend/agente/db/neo4j_importador.py`
- `backend/tests/unit/test_neo4j_importador.py`
- `backend/tests/unit/test_neo4j_importacion_api.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`

**Behavior seam and TDD cycles:**

- RED: At the importer history seam in `backend/tests/unit/test_neo4j_importador.py`, add fake-driver and injected-local-write-failure cases for durable intent, graph commit followed by local completion failure, absent marker, mismatched lineage, pre-commit exception, and retry callback; run the focused command and record the current false-completion/non-recovery failures. <!-- sdd-owner: implementation -->
- GREEN: Extend `backend/agente/db/neo4j_importador.py` with additive `neo4j-import/v2` intent/lineage fields, atomic flush/fsync/replace history writes, an idempotent graph marker, and explicit reconciliation under the existing importer lock; keep old history records readable. <!-- sdd-owner: implementation -->
- RED: At the public importer façade in `backend/tests/unit/test_neo4j_importacion_api.py`, add assertions for controlled recovery errors and stable response keys when local completion persistence fails; run the focused command and record the RED result. <!-- sdd-owner: implementation -->
- GREEN: Map recovered, failed-without-evidence, and indeterminate outcomes through the existing importer/API façade without claiming cross-system atomicity or ordinary success before local durability; preserve pre-commit failure semantics. <!-- sdd-owner: implementation -->
- TRIANGULATE: Capture Cypher and run fake sessions for committed, failed, interrupted, reconciled, mismatched, and retried paths; assert no live Neo4j or network is opened and atomic history leaves either complete old or complete new JSON. <!-- sdd-owner: implementation -->
- REFACTOR: Document durability domains, recovery states, retry idempotence, and operational handling in `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`; rerun focused tests, lint, mypy, and compile for the backend package. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_neo4j_importador.py tests/unit/test_neo4j_importacion_api.py
cd backend && python -m ruff check agente/db/neo4j_importador.py
cd backend && python -m mypy agente/db/neo4j_importador.py
cd backend && python -m compileall -q agente api scripts
```

**Authored-line forecast:** 155–210 lines.

**Finish state:** Interrupted imports have explicit deterministic outcomes; local history is atomically durable; graph callbacks are safe under driver retry; old history remains readable.

**Rollback boundary:** Revert intent/reconciliation behavior only with its focused tests/docs; do not bulk-remove graph markers or additive history/lineage fields while interrupted records may exist.

### U8 — Make relationship rollback ownership- and dependency-safe

**Capability covered:** Reverting an earlier import preserves later/shared dependencies and untagged domain relationships, supports scalar legacy ownership and future-compatible multi-owner metadata, and deletes only proven-safe edges/nodes.

**Depends on:** U7 because rollback must consume the reconciled import states and lineage model.

**Exact allowed edit surfaces:**

- `backend/agente/db/neo4j_importador.py`
- `backend/tests/unit/test_neo4j_importador.py`
- `backend/tests/unit/test_neo4j_importacion_api.py`
- `backend/README.md`
- `docs/DOCUMENTACION_TECNICA_CIAR.md`
- `openspec/changes/harden-normalizer-reliability/tasks.md` (checkbox state and implementation evidence only)

**Behavior seam and TDD cycles:**

- RED: At the revert seam in `backend/tests/unit/test_neo4j_importador.py`, add fake-graph cases for shared later `Curso–TIENE–Silabo`, legacy scalar `_ciar_import_id`, multi-owner lists, later coverage dependencies, untagged relationships, connected nodes, and unknown relationship shapes; capture current unsafe deletion failures. <!-- sdd-owner: implementation -->
- GREEN: Update graph writes and `_revertir_grafo` in `backend/agente/db/neo4j_importador.py` to retain scalar compatibility, lazily normalize/add ownership lists, pass source-declared course-syllabus dependencies, guard type-specific deletion, fail closed for unknown shapes, and delete only target-created isolated nodes/edges. <!-- sdd-owner: implementation -->
- RED: At the response contract seam in `backend/tests/unit/test_neo4j_importacion_api.py`, add assertions for additive `relaciones_conservadas`, partial-revert status, preserved existing result keys, and safe behavior for recovered imports; run the focused command and record the RED result. <!-- sdd-owner: implementation -->
- GREEN: Expose conservative retention counts and recovered-import revert eligibility through the existing importer/API façade, preserving legacy history and without destructive metadata migration. <!-- sdd-owner: implementation -->
- TRIANGULATE: Assert captured Cypher contains ownership/dependency guards and run all fake-graph scenarios offline, including retry execution; verify untagged edges and later-required edges survive while only proven-safe imported edges are removed. <!-- sdd-owner: implementation -->
- REFACTOR: Update rollback/recovery semantics in `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`, update this `tasks.md` with every unit's RED/GREEN/TRIANGULATE/REFACTOR evidence, then run the exact full offline gates below. <!-- sdd-owner: implementation -->

**Exact offline commands:**

```bash
cd backend && python -m pytest -q tests/unit/test_neo4j_importador.py tests/unit/test_neo4j_importacion_api.py
cd backend && python -m ruff check agente/db/neo4j_importador.py
cd backend && python -m mypy agente/db/neo4j_importador.py
```

**Exact final offline gates:**

```bash
cd backend && python -m pytest -q
cd backend && python -m ruff check .
cd backend && python -m mypy agente api
cd backend && python -m compileall -q agente api scripts
```

**Authored-line forecast:** 180–250 lines.

**Finish state:** Revert is conservative, lineage-aware, legacy-compatible, and cannot destroy later or untagged semantic graph structure; all eight capabilities and SDD progress evidence are recorded.

**Rollback boundary:** Revert relationship-write and rollback-query changes as one final unit; never remove legacy read support or bulk-delete ownership metadata during rollback.

## Excluded surfaces and acceptance prohibitions

The following are not implementation surfaces for this change: any frontend file, frontend polling behavior, live service configuration, external credentials, browser/Cactus execution, paid APIs, live LLM/Neo4j/LangSmith calls, destructive graph/history migrations, and the curricular analyst system prompt. The plan must not add an authentication system, resume arbitrary workers, or alter public CSV schemas.
