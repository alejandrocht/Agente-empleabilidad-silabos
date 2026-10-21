# Design: Harden Normalizer Reliability

## Status and constraints

This design implements the confirmed local-only deployment contract for the normalizer and its explicit Neo4j publication path. It covers the one critical and seven high findings in the change specification. It does not alter the curricular analyst prompt, frontend polling, the chat/dashboard access model, or the underlying FastAPI, LangGraph, or Neo4j architecture.

The implementation remains offline-testable. Tests use FastAPI/Starlette test clients, temporary directories, fake LLMs, and fake Neo4j sessions only. FastAPI `0.141.1`, Starlette `1.6.0`, and the Neo4j driver retry semantics in the lockfile are the version contract.

## Architecture overview

The change adds five deep seams while keeping existing public HTTP paths and payloads stable where possible:

| Seam | Owner | Interface responsibility |
| --- | --- | --- |
| Local administrative access | `agente/api/acceso_administrativo.py` | Decide access only from the direct ASGI peer, leaving a single replacement point for future authentication. |
| Bounded upload admission | `agente/api/normalizador.py` plus Starlette's native request-body limit | Stop oversized bodies before FastAPI multipart parsing, then stage accepted files without execution history until raw and ZIP checks pass. |
| Private import source | `normalizador/silabos/fuente_importacion.py` | Materialize and resolve one private, stable syllabus source while hiding it from public outputs. |
| Locked HITL transaction | `normalizador/silabos/transaccion_aprobaciones.py` | Own validation, lock acquisition, snapshot, mutation, rollback, and atomic writes in one critical section. |
| Import durability and graph lineage | `db/neo4j_importador.py` | Record durable local intent, write an idempotent graph marker, reconcile interrupted imports, and remove relationship ownership safely. |

The existing `GestorEjecuciones`, curricular cleanup, release gate, and importer remain the façade seams used by HTTP routes. New behavior is placed behind those façades instead of adding endpoint-specific exceptions.

## 1. Local-only administrative access

### Module and interface

Add `backend/agente/api/acceso_administrativo.py`:

```python
def peer_is_loopback(host: str | None) -> bool: ...
async def require_local_administrator(request: Request) -> None: ...
```

`peer_is_loopback` parses only `request.client.host` with `ipaddress.ip_address`. It accepts `127.0.0.1`, `::1`, and an IPv4-mapped IPv6 address only when its mapped IPv4 address is loopback. It rejects missing, malformed, DNS-name, private-LAN, and public peers. It neither resolves hostnames nor reads `Host`, `Forwarded`, `X-Forwarded-For`, `X-Real-IP`, cookies, or authorization headers.

`require_local_administrator` raises a generic `HTTPException(403)` before any route handler runs. Its error text must not echo the peer or supplied forwarding headers. The dependency is deliberately the only future-auth replacement point: a future authenticated dependency may replace this one at router inclusion without changing business routes.

### Wiring and compatibility

`backend/api/servidor.py` includes both existing routers with `dependencies=[Depends(require_local_administrator)]`:

* `/normalizador/**` is entirely protected, including reports, output download, Cactus credential submission, cancellation, and decisions.
* `/neo4j/**` is entirely protected, including `/neo4j/estado`.

Do not attach the dependency to the FastAPI application or public routers. `/health`, `/chat`, `/chat/stream`, `/preguntar`, and `/dashboard/**` retain their exact current behavior.

Starlette `TestClient` tests that exercise administrative routes must explicitly set `client=("127.0.0.1", 0)`. The string `"testclient"` is not a production loopback address and must not become a production bypass. Tests of public routes should use `client=("203.0.113.10", 0)` to prove the guard was not inadvertently applied.

## 2. Upload admission, bounded staging, and 413 cleanup

### Selected enforcement model

FastAPI `UploadFile` parameters are available only after multipart parsing. Therefore a handler-level `stat()` check or a bounded `UploadFile.file` copy alone cannot be the primary ingress control. Configure `backend/agente/api/normalizador.py`'s `APIRouter` with Starlette 1.6's native `max_body_size=MAX_UPLOAD_BYTES` per-router facility. This limit is applied at the ASGI receive boundary and returns `413` before multipart parsing, `UploadFile` spooling, execution creation, or worker scheduling.

The configured request-body ceiling includes multipart framing. This is intentionally conservative: a raw file can never exceed the configured ceiling, but a file at the exact byte ceiling may be rejected because the envelope also consumes bytes. Document this in the operator documentation rather than weakening the hard pre-parser limit with an unbounded envelope allowance. This is the technical default that guarantees a false or missing `Content-Length` cannot cause the full oversized body to be buffered by FastAPI/Starlette.

The implementation must use the locked Starlette native facility, not a custom `BaseHTTPMiddleware` that calls `request.body()`, and not `max_part_size`, which does not limit uploaded files. A focused integration test must prove the exact configured API shape on Starlette `1.6.0` and prevent a future dependency upgrade from silently removing early `413` behavior.

### Handler state machine

Refactor both `iniciar_empleabilidad` and `iniciar_silabos` in `backend/agente/api/normalizador.py` to share a private bounded-admission helper. The public successful response remains `202`; rejection is now `413` and has no execution record.

```text
request received
  -> native body limit rejects oversized Content-Length/body: 413, handler not entered
  -> handler streams accepted UploadFile to private scratch file, counting bytes
  -> raw stream crosses MAX_UPLOAD_BYTES: delete scratch, 413
  -> syllabus ZIP preflight exceeds expanded limits: delete scratch, 413
  -> gestor.crear(...)
  -> atomically move/copy scratch into <NOR>/entrada/<safe-name>
  -> schedule existing validation: 202
```

The helper will:

1. sanitize the basename as today;
2. use a `NamedTemporaryFile` or equivalent under a private scratch directory owned by `gestor_ejecuciones.base_dir`, never an execution directory;
3. read and write fixed-size chunks, incrementing before accepting each chunk, so it stops at `MAX_UPLOAD_BYTES + 1` and never calls `read()` without a bound;
4. close both the scratch file and `UploadFile.file` in `finally`;
5. unlink its scratch path on every rejection, validation error, move failure, or exception;
6. call `gestor.crear` only after raw admission and, for syllabus archives, ZIP limit preflight succeed; and
7. after `crear`, promote the scratch artifact into `entrada/` and remove the just-created execution directory if promotion or scheduling fails before ownership transfers.

This second byte counter is defense in depth and a direct unit-test seam; the native Starlette limit is still the only control that can reject an arbitrary oversized HTTP body before multipart parsing. No path uses `read()` without a size or reads the complete upload into Python memory.

### ZIP preflight

Extract a pure limit scan from `backend/agente/normalizador/silabos/entrada.py`, for example:

```python
def validar_limites_archivo(ruta: Path) -> tuple[Hallazgo, ...]: ...
def excede_limite_de_ingreso(hallazgos: Iterable[Hallazgo]) -> bool: ...
```

It reuses the current ZIP metadata checks and the constants `MAX_ARCHIVOS`, `MAX_BYTES_ARCHIVO`, and `MAX_BYTES_DESCOMPRIMIDOS`; it does not extract entries. `validar_archivo()` calls the same helper so the background validation contract is not duplicated. The HTTP admission path invokes it on the private scratch archive before creating an execution. `LIMITE_ARCHIVOS_EXCEDIDO`, `ARCHIVO_CURRICULAR_DEMASIADO_GRANDE`, and `ZIP_DESCOMPRIMIDO_DEMASIADO_GRANDE` become an HTTP `413` at this pre-history stage. Malformed archives and semantic ZIP failures retain their existing validation behavior unless they are an explicit configured size/entry limit.

A raw-limit or ZIP-limit rejection must leave no `NOR_*` directory, no file under `entrada/`, and no private scratch file. Starlette's own request-scoped spool file is not application history and is released with the request; the application must not retain or promote it.

## 3. Execution cleanup and private import source

### Stale execution cleanup

`GestorEjecuciones.__init__` remains the lifecycle owner. Immediately after creating `RepositorioEjecucionesPersistidas`, and before exposing the executor, it calls a repository method such as:

```python
def eliminar_no_terminales_sin_worker(self) -> tuple[str, ...]: ...
```

The repository iterates only direct, non-symlink `NOR_*/manifest.json` children beneath the resolved base directory. It parses a manifest, deletes its whole execution directory only when `estado` is a recognized non-terminal state, and skips malformed, symlinked, inaccessible, or unclassifiable directories. It preserves all terminal states already recognized by `es_terminal`, including their reports. Errors are best effort per directory and never prevent startup.

At a new manager initialization the in-process worker registry is empty by definition, so every valid persisted non-terminal manifest is stale. No worker is resumed, no synthetic cancel request is created, and the stale directory is not listed, fetched, cancelled, or manually deleted later. This is intentionally safe only for one local manager and one data directory; it is not a lease, PID check, or multi-process coordination mechanism.

### Stable importer artifact

Add `backend/agente/normalizador/silabos/fuente_importacion.py` with one canonical private relative path and two narrow helpers:

```python
RUTA_FUENTE_IMPORTACION = Path("importacion/silabos_fuente.jsonl")
def materializar_fuente_importacion(directorio_ejecucion: Path) -> Path | None: ...
def resolver_fuente_importacion(directorio_ejecucion: Path) -> Path | None: ...
```

The private name is fixed as:

```text
<NOR>/importacion/silabos_fuente.jsonl
```

During `_finalizar`, before `_purgar_temporales` removes `limpios/`, a syllabus execution whose `limpios/silabos.jsonl` exists copies that one file to a same-directory temporary file, flushes it, atomically replaces the stable artifact, and then permits staging cleanup. It does not preserve `limpios/`, extraction files, browser profiles, or any other staging tree. Re-finalization is idempotent: a valid stable artifact is replaced from the current staging file if available, otherwise retained.

The stable artifact is never added to `outputs`, never placed below `salidas/reportes`, and is explicitly denied by `descargar_output` even if a malformed historical manifest declares it. Existing `_filtrar_outputs_curriculares` continues its final-CSV allowlist; this extra deny rule protects the private path independently of manifest integrity. The artifact is deleted only with the entire execution directory through existing manual deletion or retention, not through routine terminal staging cleanup.

`resolver_fuente_importacion` validates that the resolved path is a regular file immediately beneath the expected private directory. It tries the stable artifact first, then the historical exact fallback `<NOR>/limpios/silabos.jsonl`. The importer uses the same logical digest label for both forms so finalization does not change a content-identical source fingerprint. Missing or invalid source produces the existing safe non-importable preview/error; it never claims a completed execution is importable merely because CSVs exist.

If a new execution has an otherwise import-allowing release gate but materialization cannot produce a valid private source, finalization adds an error hallazgo, changes the curricular result to non-publicable, and persists a release gate with `BLOCK_IMPORT` and `IMPORT_SOURCE_UNAVAILABLE`. Terminal failed/cancelled executions may retain a source only when it was already safely copied, but their existing state and release gate still prevent import.

## 4. HITL transaction ordering and rollback

`transaccion_aprobaciones.py` is the transaction implementation and `aprobaciones.py` remains the façade exposing its existing hook map. Keep the current single `_LOCK`; do not add a lock per file, execution, or catalog.

Refactor into a private operation that assumes ownership of the lock, for example `_aplicar_decisiones_bajo_bloqueo(...)`. The public transaction flow is:

```text
validate execution directory
  -> acquire hooks["_LOCK"] once
  -> derive transactional roots
  -> capture snapshot
  -> validate/plan/mutate/write/recalculate gate
  -> return committed result
on Exception while locked
  -> restore exactly this locked snapshot
  -> re-raise
release lock
```

The current `_aplicar_decisiones_curriculares` compatibility entry point acquires the lock once and calls the same private locked operation. `aplicar_decisiones_curriculares` also acquires the lock once before snapshotting and calls that private operation directly. It must not call an inner function that reacquires `hooks["_LOCK"]`; this preserves fake non-reentrant lock tests and prevents self-deadlock. The existing `RLock` remains valid but is no longer relied upon for nested lock acquisition.

Validation occurs before the lock. Root discovery, snapshot capture, all mutation and all current atomic file replacement calls occur after lock acquisition and before release. If snapshot capture fails, no rollback is attempted because no mutation has begun. If mutation fails, restoration happens before unlocking; a restoration failure is chained to the original failure and the request remains failed. Existing hook names and façade signatures remain unchanged.

## 5. Aggregate LLM analysis failure and release blocking

### Analysis result and progress

Extend `ResultadoAnalisisCurricular` additively with:

```python
fallo_agregado: bool = False
motivos_fallo: tuple[str, ...] = ()
```

These are internal/result fields, not prompt changes. Stable reasons are:

* `LLM_BATCH_INVOCATION_FAILED` for a batch call or analyst construction failure;
* `LLM_BATCH_RESPONSE_INVALID` for an unusable structured response; and
* `LLM_SOURCE_COVERAGE_INCOMPLETE` when one or more source logro identifiers lack a locally validated decision after the existing one retry.

The analyzer continues processing later batches after a failure and retains all existing success, failure, retry, and no-decision audit rows. It tracks valid decision coverage separately from progress counters; a progress counter means a batch was handled, not that it produced valid semantic coverage. A partial initial response that the existing retry fully repairs is not a final failure. A failed retry, invalid response, rejected local grounding, or absent decision leaves coverage incomplete and sets aggregate failure.

The analyzer's final progress is `fase="error"`, `reporte_final="error"` when `fallo_agregado` is true, otherwise it retains the current finalizing/completed success path. `limpieza.py` must publish the returned analyzer progress rather than overwrite an error with `completado/disponible`.

### Cleanup and gate transition

`limpieza.py` writes `analisis_llm.json` with additive `fallo_agregado` and `motivos_fallo` fields. Its status is `BLOQUEADO` for aggregate failure and `COMPLETADO` otherwise. It still writes `decisiones_llm.jsonl`, including partial successful evidence.

Add a small pure gate adjustment in `release_gate.py` (or an equivalently narrow helper) that merges an aggregate analysis failure into an existing gate:

* append the stable blocker `LLM_SEMANTIC_ANALYSIS_INCOMPLETE` once;
* record `checks["semantic_analysis"] = {"ok": false, "reasons": [...]}`;
* set `decision="BLOCK_IMPORT"`;
* return a copied gate rather than mutating an input object.

`limpieza.py` applies that adjustment after catalog construction, rewrites `release_gate.json`, appends an error hallazgo such as `ANALISIS_LLM_INCOMPLETO`, and returns `ResultadoLimpiezaSilabos(publicable=False, ...)`. `EjecutorCurricular` therefore transitions the execution to `no_publicado`; normal output filtering makes partial CSVs non-public, and the existing importer gate check blocks preview/import eligibility. Offline mode (`usar_llm=False`) creates no analysis result and remains deterministic. The analyst prompt and its source file remain unchanged.

## 6. Neo4j intent, recovery, and atomic local history

### Durability model

Neo4j graph commit and local JSON history are separate durability domains. This design does not claim a distributed transaction. It uses durable local intent before graph work, an idempotent graph commit marker, and explicit later reconciliation.

Each new history record is additive and backward compatible:

```json
{
  "version": "neo4j-import/v2",
  "id_importacion": "IMP_...",
  "id_ejecucion": "NOR_...",
  "fingerprint": "...",
  "estado": "en_progreso",
  "creada_en": "...",
  "actualizada_en": "...",
  "resumen": {"...": 0},
  "intento": {
    "plan_hash": "sha256 of canonical planned new rows and required course-syllabus pairs",
    "lineage": {"id_ejecucion": "...", "fingerprint": "..."}
  }
}
```

`_escribir_historial` writes a unique temporary sibling, flushes and `fsync`s the file, atomically uses `os.replace`, and `fsync`s the parent directory where supported. The writer retains at most the existing 100 records. It removes its temporary file on failure. Failure to durably write initial intent prevents graph work; failure to durably mark a graph-successful import completed causes an error response and deliberately leaves the durable intent as `en_progreso`.

### Graph marker and state transitions

At the start of `_escribir_grafo`'s managed transaction callback, merge one marker:

```cypher
MERGE (m:CiarImportacion {id_importacion: $import_id})
ON CREATE SET m.id_ejecucion = $execution_id,
              m.fingerprint = $fingerprint,
              m.plan_hash = $plan_hash,
              m._ciar_import_marker = true
```

The marker, all domain writes, ownership updates, and course-reversion records are in the same managed transaction. Every operation uses `MERGE`, `ON CREATE`, deterministic properties, or idempotent ownership-list normalization, so a Neo4j driver retry has the same graph result as one execution.

The import state machine is:

```text
planned -> en_progreso (local intent durable)
        -> graph transaction fails pre-commit -> fallida
        -> graph transaction commits -> completada (local completion durable)

process/local-write interruption after graph commit:
en_progreso + matching graph marker -> completada_recuperada
 en_progreso + no marker/no legacy evidence -> fallida (recovery=no_graph_evidence)
 en_progreso + mismatched marker/lineage -> indeterminada (manual-safe, no success claim)
```

`completada_recuperada` is deliberately distinct from ordinary `completada`. It includes a persisted `recuperacion` object with evidence type and reconciliation timestamp, and is revertible. `indeterminada` is not importable or revertible automatically. Existing history records without `version` or marker remain readable; their old terminal states retain their meaning.

`historial()`, `importar()` before starting a new import, and `revertir()` before evaluating the target invoke internal reconciliation under the existing importer `RLock`. Reconciliation queries the marker and, for legacy `en_progreso` records, conservative old graph evidence (`_ciar_import_id` on created nodes/relationships or a `CiarImportacionCursoReversion` record). It updates local state only when evidence and intent lineage are consistent. If Neo4j cannot be queried, it leaves `en_progreso` intact and reports it as unresolved rather than inventing a terminal result.

When local completion persistence fails after a graph commit, the HTTP call returns a controlled import-history recovery error, never an ordinary success payload. A later history call reconciles the same intent. Existing pre-commit failures keep the current `fallida` behavior.

## 7. Relationship ownership and safe rollback

### Forward-compatible metadata without migration

New relationship writes retain legacy scalar metadata and add a list:

* `_ciar_import_id`: original creator, preserved for legacy readers;
* `_ciar_import_created`: true only if the relationship was first created by an import; and
* `_ciar_import_ids`: ordered, unique import IDs that created or subsequently required the semantic edge.

On `MERGE ... ON CREATE`, write both the scalar and a singleton list. On `ON MATCH`, lazily normalize the ownership list from the legacy scalar when present and append the current import ID only if absent. Do not set `_ciar_import_created` on a pre-existing untagged domain relationship; it may receive a reference list for lineage but is never made deletable by this change.

For course-syllabus pairs, pass all source-declared pairs (not only new pairs) to the relationship writer so a later import explicitly records its dependency on an already-existing `Curso-[:TIENE]->Silabo` edge. Preview counts remain based on newly created pairs; the lineage write is not represented as a new-domain-data count. The same normalization applies to importer-created `ENSENIA`, `TIENE`, `CUBRE`, and coverage-to-skill/tool edges whenever the importer touches them.

No global graph migration occurs. A relationship with only scalar `_ciar_import_id` is interpreted as a one-element ownership list during update or rollback. An untagged relationship remains outside rollback ownership.

### Rollback algorithm

`revertir()` builds `ids_supervivientes` from all non-reverted completed or recovered imports, conservatively including unresolved `en_progreso` IDs with graph evidence. `_revertir_grafo()` executes one retry-safe transaction that:

1. finds only relationships attributable to the target through the legacy scalar or ownership list and having `_ciar_import_created=true`;
2. removes the target from the normalized ownership list;
3. deletes a relationship only when no surviving ownership remains **and** a type-specific dependency query proves no surviving imported node or coverage requires the semantic edge;
4. preserves relationships with surviving owners or dependencies, clearing/repointing stale scalar ownership rather than continuing to attribute them solely to the reverted import;
5. deletes target-created nodes only when isolated after guarded relationship handling;
6. retains and reports nodes that are still connected; restores course metadata using the existing reversion records; and
7. deletes the matching `CiarImportacion` graph marker after the target's graph changes are complete.

The dependency guards are deliberately conservative:

* For `Curso-[:TIENE]->Silabo`, retain the edge when any surviving or untagged `Cobertura_Curricular` has the same `id_curso` and `id_silabo`.
* For `Carrera-[:ENSENIA]->Curso`, retain the edge when surviving or untagged coverage still depends on that course.
* For coverage-adjacency edges, remove only when the associated coverage is target-owned and no surviving ownership/dependency remains.
* Unknown relationship shapes fail closed: they remain rather than being deleted.

The rollback response adds `relaciones_conservadas` while preserving existing result keys. A rollback with any retained relationship or node remains `revertida_parcial`; otherwise it is `revertida`. This may leave conservative graph residue, but it cannot destroy a later import's semantic edge. There is no destructive metadata migration and no deletion of untagged domain relationships.

## Data and compatibility summary

| Data | New representation | Read compatibility | Write/cleanup rule |
| --- | --- | --- | --- |
| Execution source | `importacion/silabos_fuente.jsonl` | Falls back to `limpios/silabos.jsonl` | Stable copy before staging purge; private; removed only with whole execution history. |
| Execution manifests | Existing terminal vocabulary | All existing manifests remain readable | New manager deletes only parseable recognized non-terminal directories at startup. |
| LLM audit | Add aggregate failure/reason fields | Existing readers ignore additive fields | Keep successful and failed JSON/JSONL audit evidence. |
| Import history | `neo4j-import/v2` intent/recovery fields | Existing records stay readable | fsync + atomic replacement; no false success after local-write failure. |
| Graph relationships | Scalar creator plus `_ciar_import_ids` | Scalar-only edges are interpreted lazily | No bulk migration; untagged edges never become deletable. |
| Graph imports | `CiarImportacion` commit marker | Legacy tag/reversion evidence supported | Marker is created/removed within idempotent graph transactions. |

## Files expected to change

### Production

* `backend/api/servidor.py` — attach the one administrative dependency at the routing seam.
* `backend/agente/api/acceso_administrativo.py` — new replaceable direct-loopback guard.
* `backend/agente/api/normalizador.py` — bounded private staging, `413` mapping, scratch cleanup, and private-output denial.
* `backend/agente/normalizador/silabos/entrada.py` — reusable ZIP size/entry preflight.
* `backend/agente/normalizador/ejecuciones.py` — startup stale execution deletion orchestration and stable-source finalization ordering.
* `backend/agente/normalizador/persistencia_ejecuciones.py` — safe scan/delete of parseable non-terminal manifests.
* `backend/agente/normalizador/silabos/fuente_importacion.py` — new stable private artifact resolver/materializer.
* `backend/agente/normalizador/modelos.py` — only additive analysis progress/result typing if required by the chosen result exposure.
* `backend/agente/normalizador/silabos/analista_llm.py` — aggregate batch/coverage failure tracking and final progress state.
* `backend/agente/normalizador/silabos/limpieza.py` — audit serialization and semantic failure-to-gate transition; no prompt edit.
* `backend/agente/normalizador/silabos/release_gate.py` — pure aggregate-analysis blocker merger.
* `backend/agente/normalizador/silabos/transaccion_aprobaciones.py` — single-owner lock/snapshot/rollback ordering.
* `backend/agente/db/neo4j_importador.py` — durable intent/history, marker reconciliation, idempotent ownership lists, and guarded rollback.

### Tests

* `backend/tests/unit/test_normalizador_api.py` — loopback test-client helper, early `413`, no manifest/scratch residue, valid admission, ZIP-limit rejection, and private output denial.
* `backend/tests/unit/test_normalizador_ejecuciones.py` — stale non-terminal deletion, terminal preservation, stable-source lifecycle, and legacy source fallback fixtures.
* `backend/tests/unit/test_normalizador_silabos.py` — ZIP limit preflight and aggregate analysis release blocking.
* `backend/tests/unit/test_normalizador_analista_llm.py` — one successful plus one failing fake batch, invalid response, missing coverage, repaired retry, retained reports, and error progress.
* `backend/tests/unit/test_normalizador_aprobaciones.py` — deterministic validate → lock → snapshot → mutate/rollback order and no nested acquisition with a non-reentrant recording lock.
* `backend/tests/unit/test_neo4j_importador.py` — fake marker graph, injected history-write failures, recovery states, retry-idempotent Cypher, scalar legacy ownership, multi-owner retention, shared coverage, and untagged edge preservation.
* `backend/tests/unit/test_neo4j_importacion_api.py` — loopback client configuration and unchanged endpoint payload façade behavior.

Existing administrative-route tests in `test_normalizador_ejecuciones.py` and `test_normalizador_aprobaciones.py` also need explicit loopback clients. Public-only tests such as dashboard and conversation tests need new non-loopback assertions but must not adopt an administrative bypass.

### Documentation/configuration

* `backend/README.md` — local-only guard, no proxy/forwarded-header support, multipart-body accounting, private artifact behavior, single-instance startup deletion, semantic blocking, and import recovery/partial rollback semantics.
* `docs/DOCUMENTACION_TECNICA_CIAR.md` — update the normalizer state, ingress, local operation, import durability, and rollback diagrams/text.
* `backend/.env.example` — document `NORMALIZADOR_MAX_UPLOAD_BYTES` explicitly as an HTTP request-body ceiling including multipart framing. No authentication secret is added because the confirmed product choice is loopback-only access.

## Offline verification plan

Tests are written RED → GREEN by public seam and do not invoke OpenAI, Neo4j, LangSmith, a browser, Cactus, or paid services.

1. Use a FastAPI test app/client with explicit `client=("127.0.0.1", 0)` and `client=("203.0.113.10", 0)` to prove both guard outcomes and forwarding-header irrelevance.
2. Use a small native body limit with `TestClient` to assert `413` before a route probe runs; use bounded `BytesIO` helpers for absent/lying metadata and verify no scratch or `NOR_*` directory remains.
3. Build tiny ZIPs whose `ZipInfo` metadata crosses one entry-count, entry-size, and expanded-total threshold; assert `413`, no execution history, and no source retained.
4. Use temporary persisted manifests to prove new-manager deletion of valid stale states and preservation of every terminal/report fixture.
5. Use a recording non-reentrant fake lock and hook map to prove lock ordering and rollback locality without thread timing.
6. Use fake LLMs that succeed, raise, return invalid structured output, omit then repair, and omit permanently; assert aggregate state, evidence preservation, `BLOCK_IMPORT`, and `no_publicado` only where appropriate.
7. Use fake driver/session/transaction objects to capture Cypher and simulate: pre-commit exception, graph-marker commit plus local replacement failure, marker recovery, absent evidence, mismatched lineage, and callback retry.
8. Use fake graph scenarios for scalar-only, ownership-list, later shared course-syllabus coverage, and untagged relationships; assert only proven-safe edges are deleted.
9. Run the configured offline quality gates after implementation:

```text
cd backend && python -m pytest -q
cd backend && python -m ruff check .
cd backend && python -m mypy agente api
cd backend && python -m compileall -q agente api scripts
```

## Delivery, migration, and rollback

The effective delivery strategy is `auto-chain` with a 400 changed-line review budget. Chain selection remains deferred, so this is a dependency-ordered migration forecast rather than a chosen PR stack:

1. **Administrative boundary and ingress:** loopback guard, native `413`, bounded staging, API tests, and operator notes. This reduces immediate exposure first.
2. **Execution lifecycle and source artifact:** startup stale deletion, stable private source, importer fallback, lifecycle/privacy tests, and single-instance docs.
3. **Semantic and HITL correctness:** aggregate LLM failure gate followed by the lock-before-snapshot transaction refactor, with fakes and no prompt changes.
4. **Import intent and reconciliation:** atomic local history, marker, recovery state handling, and fake-driver failure/retry tests.
5. **Relationship-safe revert:** additive ownership lists, guarded dependency deletion, legacy compatibility, and conservative rollback tests.

Each work unit includes its tests and docs. If the implementation forecast for a unit crosses 400 changed lines, auto-chain creates cohesive review slices rather than omitting tests or compressing safety behavior.

Rollback is also by work unit:

* Reverting unit 1 removes the loopback/body-boundary behavior only; it does not create retained oversized artifacts or execution history retroactively.
* Reverting unit 2 cannot restore stale directories already deleted at a prior startup. Restore code only after an explicit operator decision; stable artifact readers retain the legacy fallback during any transition.
* Reverting unit 3 restores the old release behavior only as a deliberate safety rollback; the added audit fields are additive and can remain readable. No prompt rollback exists because no prompt changes occur.
* Reverting unit 4 leaves graph markers and additive history fields readable by backward-compatible code, but automatic recovery should not be removed while interrupted `en_progreso` records exist.
* Reverting unit 5 must preserve read support for `_ciar_import_ids`; do not bulk-remove ownership metadata. Conservative retained relationships are safe residue and must not be deleted during rollback.

No phase performs a destructive graph or history migration. Live acceptance against Neo4j or an LLM is explicitly deferred from this change.
