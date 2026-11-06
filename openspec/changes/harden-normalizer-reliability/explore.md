# Exploration — harden-normalizer-reliability

## Scope

This exploration is limited to the one critical and seven high-severity findings confirmed by the user at rollback tree `953eb6d`:

1. Critical: admin normalizer and Neo4j routes lack authentication.
2. High: `_finalizar()` purges `limpios/` before Neo4j preview/import.
3. High: active executions become uncancellable zombies after process restart.
4. High: HITL snapshot/rollback can undo a successful concurrent mutation.
5. High: per-batch LLM failures can aggregate as `COMPLETADO`/successful completion.
6. High: Neo4j transaction can commit before local history records completion.
7. High: rollback can delete shared relationships reused by later imports.
8. High: upload/ZIP limits are enforced too late.

Explicitly excluded: the medium frontend polling issue.

No live LLM, Neo4j, LangSmith, browser, or paid API was used. No functional source code was modified.

## Project context read

- `openspec/config.yaml`
- `openspec/project-context.md`
- `AGENTS.md`
- `CLAUDE.md`
- Relevant backend code under `backend/agente/**` and API wiring under `backend/api/servidor.py`.

Delivery note: `openspec/config.yaml` records the current effective delivery strategy as `auto-chain` with a 400-line review budget. The later explicit user correction supersedes the earlier preflight default; chain strategy remains deferred until the tasks forecast determines the final review slices.

## Public seams and root causes

### 1. Admin normalizer and Neo4j routes lack authentication

**Public seams**

- FastAPI app mounting: `backend/api/servidor.py` includes `normalizador_router` at `/normalizador` and `neo4j_importacion_router` at `/neo4j`.
- Normalizer routes: `backend/agente/api/normalizador.py` exposes upload, Cactus extraction with credentials, cancellation, execution history, reports, output downloads, quarantine, pending decisions, and HITL decision mutation.
- Neo4j publication routes: `backend/agente/api/neo4j_importacion.py` exposes `/neo4j/estado`, `/neo4j/validar`, `/neo4j/importar`, `/neo4j/importaciones`, and `/neo4j/importaciones/{id}/revertir`.

**Root cause**

Routers are mounted without a dependency or middleware requiring an operator/admin credential. The modules import only FastAPI route primitives and business adapters, not `Depends`, `Security`, or an auth guard. Existing anonymous cookie logic protects conversation memory identity only and is not an authorization boundary.

**Minimal safe solution options**

- Smallest safe option: add a reusable admin dependency that validates a constant-time bearer token or header secret from env, then attach it to the two admin routers at include time or router construction.
- Safer compatibility option: keep `/neo4j/estado` optionally public only if product requires unauthenticated status; otherwise protect all `/neo4j` and `/normalizador` routes uniformly.
- Avoid building a user/role system unless required; a single server-side admin secret is sufficient for this critical hardening slice.

**Compatibility constraints**

- Existing tests instantiate `TestClient(servidor.app)` and will need an offline test secret/header helper.
- Do not break `/health`, `/chat`, `/chat/stream`, `/preguntar`, or dashboard read-only routes.
- Avoid echoing secrets in 401/403 responses or logs.

**Offline test seams**

- FastAPI `TestClient` against `servidor.app` with monkeypatched env/config.
- Assert protected endpoints reject missing/wrong credentials and accept the test credential.
- Assert public conversational/dashboard routes remain unaffected.

### 2. `_finalizar()` purges `limpios/` before Neo4j preview/import

**Public seams**

- Terminal cleanup: `GestorEjecuciones._finalizar()` and `_purgar_temporales()` in `backend/agente/normalizador/ejecuciones.py`.
- Import source loader: `ImportadorNeo4j._cargar_fuente()` in `backend/agente/db/neo4j_importador.py` requires `limpios/silabos.jsonl` after checking CSV outputs.
- User-facing endpoints: `/neo4j/validar` and `/neo4j/importar` call `previsualizar()`/`importar()`.

**Root cause**

For terminal syllabus executions, `_purgar_temporales()` deletes `limpios/`, but the Neo4j importer treats `limpios/silabos.jsonl` as authoritative for syllabus-to-course integrity and fingerprinting. The manifest may advertise importable CSV outputs while a later preview/import cannot load its required source.

**Minimal safe solution options**

- Preserve only `limpios/silabos.jsonl` for syllabus executions until import retention expires; continue deleting bulky transient extraction artifacts.
- Better locality: materialize an import-owned, minimal `salidas/reportes/silabos_import_source.jsonl` or equivalent during normalizer completion and have the importer read that stable artifact instead of a staging path.
- Avoid making all of `limpios/` public or long-lived if only one small file is needed.

**Compatibility constraints**

- `CLAUDE.md` says `limpios/silabos.jsonl` is not a final result; preserving/mirroring it must not expose it via public output download.
- Existing output filtering must still hide pre-HITL or non-public reports.
- Historical manifests may lack the stable artifact; importer may need a compatibility fallback to `limpios/silabos.jsonl` where present.

**Offline test seams**

- Unit test `GestorEjecuciones._finalizar()` on a syllabus execution with `limpios/silabos.jsonl` and temporary siblings.
- Importer unit tests using `_manifest_y_salidas()` fixtures can assert preview works after finalization-like cleanup.

### 3. Active executions become uncancellable zombies after process restart

**Public seams**

- Cancellation endpoint: `POST /normalizador/ejecuciones/{id}/cancelar` calls `gestor_ejecuciones.cancelar()`.
- Active object registry: `GestorEjecuciones._ejecuciones` in `backend/agente/normalizador/ejecuciones.py`.
- Persistence repository: `RepositorioEjecucionesPersistidas.obtener()` reads a manifest when the object is not active, but `_obtener_objeto()` only checks in-memory state.

**Root cause**

Cancelable state lives in process memory (`Ejecucion.cancelada` Event and `_ejecuciones`). After restart, manifests may still show `validando`, `limpiando`, or `normalizando`, but no worker object exists. `cancelar()` uses `_obtener_objeto()` and returns 404 instead of marking the persisted execution terminal/cancelled. History deletion also may treat the manifest as active forever.

**Minimal safe solution options**

- On `GestorEjecuciones` startup, reconcile persisted non-terminal manifests to a terminal `error` or `cancelado`-like interrupted state with an audit hallazgo.
- For `cancelar()` on a non-active but persisted non-terminal manifest, update the manifest to a terminal interrupted/cancelled state and create minimal cancellation reports.
- Do not attempt to resume arbitrary in-flight Python work after restart; that is larger and riskier than marking stale work interrupted.

**Compatibility constraints**

- Preserve active in-process cancellation semantics for current executions.
- Preserve terminal history readability and report download behavior.
- Choose a state accepted by existing terminal-state policy or update it consistently.

**Offline test seams**

- Create a manifest in `validando` or `normalizando`, instantiate a new `GestorEjecuciones(tmp_path)`, and assert list/get/cancel/delete behavior is no longer zombie-like.
- Unit-level direct tests avoid threads, LLM, Cactus, and browser.

### 4. HITL snapshot/rollback can undo a successful concurrent mutation

**Public seams**

- Decision endpoint: `POST /normalizador/ejecuciones/{id}/pendientes/decidir`.
- Transaction facade: `aplicar_decisiones_curriculares()` in `backend/agente/normalizador/silabos/transaccion_aprobaciones.py`.
- Global lock is acquired inside `_aplicar_decisiones_curriculares()`, after `_capturar_arboles()` has already captured transactional roots.

**Root cause**

The wrapper captures snapshots before entering the lock. If two calls overlap, call A can capture old state, call B can acquire the lock and commit, then call A can fail and restore its old snapshot, undoing B's successful mutation. The rollback scope includes execution/report/catalog roots, so the blast radius is broad.

**Minimal safe solution options**

- Move snapshot capture inside the same lock that guards mutation, before any writes and after validating the directory.
- Keep rollback only for the mutation that holds the lock; never restore a snapshot captured outside the critical section.
- If the current lock is global and already available in hooks, use it; do not introduce a new lock hierarchy unless required.

**Compatibility constraints**

- Preserve existing hook seams used by tests.
- Avoid deadlocks if `_aplicar_decisiones_curriculares()` also enters the same lock; the current hook lock must be reentrant or the lock ownership must be centralized in one place.
- Continue using atomic file writes inside the critical section.

**Offline test seams**

- Unit test with fake hooks where first call captures, second mutates, first fails; assert rollback cannot remove the second mutation after the fix.
- Simpler deterministic test: assert hook call order is validate -> lock enter -> snapshot -> mutate -> rollback on exception.

### 5. Per-batch LLM failures can aggregate as `COMPLETADO`/successful completion

**Public seams**

- Analyzer: `analizar_registros_curriculares()` in `backend/agente/normalizador/silabos/analista_llm.py`.
- Execution state mapper: `EjecutorCurricular.validar_silabos()` sets `limpiado`, `limpiado_con_advertencias`, or `no_publicado` based on `limpieza.publicable` and hallazgo severities.
- Progress/report contract: `ProgresoLimpiezaLLM.reporte_final` and report entries under `analisis_llm.json`/`decisiones_llm.jsonl`.

**Root cause**

A failed LLM chunk is recorded as a report with `estado: ERROR`, but the loop marks its logros/syllabi processed and continues. Final progress publishes `finalizando` without an explicit failed final state, and the returned `ResultadoAnalisisCurricular` does not expose an aggregate failure flag. Downstream code can interpret full progress as completed even when some chunks produced no decisions.

**Minimal safe solution options**

- Track `errores_lote`/`respuestas_invalidas` in the analyzer and set final progress/report status to `error` or a blocked state when any batch failed.
- Add a blocking hallazgo to the syllabus cleanup result when the analyzer reports batch failures, forcing `no_publicado` and release gate `BLOCK_IMPORT`.
- Keep partial audit reports; do not discard successful chunk decisions, but do not call the execution successful/importable.

**Compatibility constraints**

- Offline mode (`NORMALIZADOR_CURRICULAR_LLM=false`) must remain deterministic and not require live LLM.
- Existing behavior where invalid individual decisions become human-review reports can remain non-fatal only if every source logro receives coverage and no invocation failed.
- Frontend may rely on progress fields; add fields conservatively rather than renaming existing ones.

**Offline test seams**

- Fake LLM that raises for one chunk and succeeds for another; assert aggregate result contains a failure marker and final progress is not successful/completed.
- `EjecutorCurricular.validar_silabos()` fake `limpiar_silabos` result with error hallazgo to assert `no_publicado`.

### 6. Neo4j transaction can commit before local history records completion

**Public seams**

- Import endpoint: `POST /neo4j/importar`.
- `ImportadorNeo4j.importar()` in `backend/agente/db/neo4j_importador.py` writes local `en_progreso`, calls `_escribir_grafo()`, then replaces local history with `completada`.
- History endpoint and revert endpoint depend on `historial.json` state.

**Root cause**

Graph commit and local JSON history update are not atomic. If `_escribir_grafo()` commits successfully but `_reemplazar_historial(completada)` fails or the process crashes before it, Neo4j contains created nodes/relationships tagged with `_ciar_import_id`, while local history remains `en_progreso`. Revert then refuses because only `completada` imports are revertible.

**Minimal safe solution options**

- Treat `en_progreso` with graph evidence as recoverable: add a repair/reconciliation path that can mark completion if tagged graph writes exist for that import id.
- Record enough planned import metadata before graph write so a recovery can safely decide whether an `en_progreso` import committed, failed, or is indeterminate.
- Least-code route: allow revert of `en_progreso` records after checking graph tags exist and mark result `revertida_parcial`/`revertida` with an interrupted-completion note.

**Compatibility constraints**

- Must not claim success to the caller before local history is durable unless recovery is deterministic.
- Existing `fallida` behavior for exceptions thrown before commit should remain.
- Do not require live Neo4j in tests; use fake session/driver queries.

**Offline test seams**

- Fake `_escribir_grafo()` succeeds and `_reemplazar_historial()` raises; assert recovery/revert behavior through local history and fake graph evidence.
- Fake driver query for tagged entities/relationships to exercise reconciliation without Neo4j.

### 7. Rollback can delete shared relationships reused by later imports

**Public seams**

- Revert endpoint: `POST /neo4j/importaciones/{id_importacion}/revertir`.
- `ImportadorNeo4j._revertir_grafo()` deletes all relationships with `_ciar_import_id = id` and `_ciar_import_created = true` before deleting created isolated nodes.
- Import write queries tag relationships only on `ON CREATE` for `ENSENIA`, `TIENE`, `CUBRE`, and coverage-to-catalog relationships.

**Root cause**

Relationship ownership is single-import metadata. A later import can rely on a relationship created by an earlier import without adding its own reference/ownership. Reverting the earlier import deletes the relationship even though later imported coverage or courses still need it. The node conservation check does not protect relationships.

**Minimal safe solution options**

- Before deleting a relationship, prove no later completed import depends on the same semantic edge, or maintain a reference list/set of import ids per relationship.
- Minimal query-level guard: delete tagged relationships only when no remaining created node/cobertura from a different non-reverted import requires that edge.
- More robust but larger: switch `_ciar_import_id` on relationships to `_ciar_import_ids` ownership arrays and remove only the current id, deleting the relationship only when the array becomes empty.

**Compatibility constraints**

- Existing graphs have scalar `_ciar_import_id`; migration/revert logic must support both scalar legacy and list future metadata.
- Relationship types are semantically overloaded (`ENSENIA` appears from course-to-career and coverage-to-hability/tool), so guards must match node labels and relationship meaning.
- Avoid deleting domain relationships that predated import and were never tagged as import-created.

**Offline test seams**

- Fake transaction captures generated Cypher; assert relationship deletion includes dependency guards or ownership-list semantics.
- Fake graph scenario with two imports sharing `Curso-[:TIENE]->Silabo` and coverage from later import; revert earlier must preserve the shared edge.

### 8. Upload/ZIP limits are enforced too late

**Public seams**

- Upload endpoints: `POST /normalizador/empleabilidad` and `POST /normalizador/silabos`.
- Current size limit: `MAX_UPLOAD_BYTES` in `backend/agente/api/normalizador.py`, checked only after `shutil.copyfileobj()` writes the full uploaded file to disk and creates an execution.
- ZIP expanded limits: `backend/agente/normalizador/silabos/entrada.py` checks entries after the ZIP is already accepted and stored.

**Root cause**

The boundary allocates execution directories and writes full request bodies before enforcing the configured upload limit. ZIP metadata limits are applied only after full upload persistence. This enables disk pressure and unnecessary history churn from oversized inputs.

**Minimal safe solution options**

- Stream-copy with a byte counter and abort as soon as `MAX_UPLOAD_BYTES + 1` is crossed; then mark rejection and remove/avoid retained oversized payload.
- If `Content-Length` is present and too large, reject before creating an execution directory; still handle missing/lying headers with streaming enforcement.
- For ZIPs, keep metadata validation in `validar_archivo()` but ensure the raw upload cannot exceed the outer limit before validation.

**Compatibility constraints**

- Multipart uploads may not always include trustworthy `Content-Length` per file.
- Existing API returns `202` with a rejected execution object for oversized files; switching to `413` before creating an execution is safer but changes compatibility. Decide in proposal/spec.
- Avoid reading entire files into memory.

**Offline test seams**

- `TestClient` uploads a stream over a monkeypatched small `MAX_UPLOAD_BYTES`; assert copy stops early and does not retain the full oversized payload.
- Unit-test a bounded copy helper with `BytesIO` to avoid large fixtures.

## Cross-issue dependencies

1. Authentication should be first. It reduces exposure while reliability fixes are developed and reviewed.
2. Stable import artifacts (`limpios/silabos.jsonl` preservation or mirror) must precede Neo4j preview/import reliability tests.
3. Upload early rejection should land before or with execution reconciliation because it changes when execution records are created.
4. Zombie reconciliation and HITL rollback both touch persisted execution state; they should coordinate terminal-state vocabulary and manifest audit hallazgos.
5. Neo4j history recovery and shared-relationship rollback should be designed together because both depend on import lineage metadata and reversible ownership semantics.
6. LLM batch aggregation affects release gate/import eligibility; it should land before final importer acceptance tests so failed semantic analysis cannot produce importable outputs.

## Compatibility and migration concerns

- Existing manifests may be non-terminal after a prior crash. Startup or access-time reconciliation needs a one-time safe migration path.
- Existing import histories may contain `en_progreso` records from successful graph commits; recovery must not assume local JSON is authoritative when graph tags exist.
- Existing Neo4j relationship metadata is scalar `_ciar_import_id`; any future multi-owner metadata must handle legacy scalar tags.
- Existing frontend/API tests expect unauthenticated admin endpoints; tests and local developer instructions need a deterministic admin secret convention.
- Existing public output filtering must continue to hide staging and pre-HITL artifacts even if importer-required source files are preserved.
- Retention cleanup must not delete import-required artifacts for executions whose imports are still reversible, unless importer history no longer needs them.

## Offline verification plan

- Use backend unit tests only with fakes/contracts: `pytest` targeted tests under `backend/tests/unit/`.
- Use `TestClient` for FastAPI auth and upload boundary behavior.
- Use fake `GestorEjecuciones(tmp_path)` and manifests for zombie/reconciliation tests.
- Use fake hook maps and temporary directories for HITL transaction ordering and rollback tests.
- Use fake LLM objects that return structured output or raise; never call `obtener_llm()` live.
- Use fake Neo4j driver/session/transaction objects and captured Cypher/records; never connect to Neo4j.
- Keep LangSmith disabled by existing `backend/tests/conftest.py` controls.

## Curricular analyst system prompt read-only assessment

Source reviewed: `_prompt_analista()` in `backend/agente/normalizador/silabos/contexto_analista.py` plus its structured-output models in `backend/agente/normalizador/silabos/analista_llm.py`.

### Strengths

- It clearly states the syllabus is the only source of truth.
- It requires one decision per logro and same-order output, which supports deterministic Python-side correlation.
- It forbids invented identifiers and control codes, leaving ID authority in Python.
- It requires exact evidence fragments and a professional verb-object skill shape.
- It injects a sanitized career profile instead of raw internal profile metadata.
- Pydantic structured-output models constrain lengths, confidence range, and list sizes.

### Ambiguities

- It asks to represent all specific outcomes while also allowing `requiere_revision=true`; the expected behavior for weak/ambiguous evidence could be more explicit.
- It says tools only when they appear in evidence, but does not define whether program topics, bibliography, software names in examples, or teaching resources count as evidence.
- It says do not use other-career taxonomies, but does not state what to do when the delivered profile is incomplete or irrelevant.
- It asks for `logro` literal text while also saying not to return identifiers; models may still confuse the literal with an ID-like correlator.

### Token waste

- The full sanitized profile is dumped with pretty JSON indentation for every batch; this is readable but expensive.
- `CASOS` are also pretty-printed, duplicating field names and whitespace in every call.
- Repeated instruction paragraphs could be compressed once the structured schema carries part of the contract.
- Grouping by syllabus helps context quality but can create large prompts when one syllabus has many outcomes.

### Safety and structured-output risks

- The prompt depends on exact evidence copying, but enforcement is post-hoc; failed grounding currently risks becoming only a report unless aggregate failure blocks publication.
- The model is asked to create new concepts, which is product-required but inherently increases ontology drift; human approval mitigates this only if release gate remains strict.
- If partial structured output omits decisions, retry behavior exists, but total batch failure currently needs stronger aggregate blocking.
- Prompt-injection text inside syllabus fields is not explicitly named as untrusted content in the prompt; Python validation mitigates some effects, but the model instruction hierarchy could be clearer.

### Recommendations

1. Add an explicit untrusted-content rule: syllabus/profile text may contain instructions and must be treated only as data.
2. State that uncertain, unsupported, or conflicting cases must still return a decision with `requiere_revision=true`, low confidence, and exact evidence, not invented content.
3. Compact JSON with `separators=(",", ":")` or a smaller schema for prompt transport if token pressure matters.
4. Clarify allowed tool evidence sources and excluded teaching-resource/bibliography patterns in prompt language.
5. Preserve Python as the enforcement authority: structured schema, grounding validation, order/literal checks, and release-gate blocking should remain outside the prompt.

## Likely review slices

Given the 400-line review budget, current `auto-chain` delivery strategy, and eight findings, implementation should be forecast into chained review slices when tasks are written. The exact chain strategy remains deferred until that task forecast confirms scope and dependencies.

1. **Admin boundary hardening**: auth dependency, router protection, API tests, docs/config note.
2. **Upload and execution lifecycle**: bounded upload copy, stale execution reconciliation/cancellation, tests.
3. **Stable import source and LLM failure gating**: preserve/mirror import source, aggregate batch-failure blocking, release gate tests.
4. **HITL transaction safety**: move snapshot under lock and add concurrency/order tests.
5. **Neo4j import/revert lineage**: commit-history recovery, reversible `en_progreso`, shared relationship protection, fake-driver tests.

## Open questions for proposal/spec

- Should admin endpoints return `401/403`, or should oversized unauthenticated uploads be rejected before auth details are evaluated? Recommendation: auth first, then size handling.
- Should oversized uploads preserve a rejected execution record or return `413` without history? Recommendation: prefer `413` before execution creation when `Content-Length` proves oversize; otherwise stream-abort and mark a rejected execution only if already created.
- Should stale in-progress manifests become `cancelado`, `error`, or a new terminal state such as `interrumpido`? Recommendation: reuse existing terminal vocabulary unless API consumers need a distinct interrupted state.
- Should relationship ownership migrate to arrays now or use guarded deletes first? Recommendation: guarded deletes are the minimal safe patch; ownership arrays are a follow-up if rollback semantics keep expanding.

## Non-goals

- No frontend polling changes.
- No live Neo4j, LLM, LangSmith, browser, or paid API verification.
- No functional source-code changes during this exploration.
- No replacement of the current FastAPI, LangGraph, or Neo4j architecture.
