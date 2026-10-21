# Normalizer Reliability Specification

## Purpose

This change hardens the local normalizer and Neo4j publication workflow at their public HTTP, execution, analysis, transaction, and import seams. The deployment contract is one local instance with one data directory. Verification SHALL be deterministic and offline, using FastAPI test clients and fakes or contracts for LLM and Neo4j boundaries.

The medium frontend polling issue and all curricular analyst prompt edits are explicitly out of scope. Health, conversation, and dashboard routes remain outside the administrative access change.

## Requirements

### Requirement: Replaceable loopback-only administrative access

The system SHALL apply one replaceable administrative access guard to every route under `/normalizador/**` and `/neo4j/**`. The guard SHALL authorize only a direct peer address representing loopback, including `127.0.0.1`, `::1`, and supported platform-equivalent loopback forms. It SHALL NOT treat `Host`, `X-Forwarded-For`, or other forwarded/request headers as authorization. The deployment documentation SHALL state that reverse-proxy and multi-host operation are unsupported until real authentication replaces this guard.

#### Scenario: Local administrative request is allowed

- GIVEN an administrative request whose direct peer is a supported loopback address
- WHEN the request reaches a route under `/normalizador/**` or `/neo4j/**`
- THEN the request is evaluated by the administrative route

#### Scenario: Non-loopback administrative request is rejected

- GIVEN an administrative request whose direct peer is not a supported loopback address
- WHEN the request reaches any route under `/normalizador/**` or `/neo4j/**`
- THEN the request is rejected before the administrative operation runs
- AND no credentials or request headers can override the rejection

#### Scenario: Forwarded headers do not expand trust

- GIVEN a non-loopback direct peer that supplies a loopback value in `Host`, `X-Forwarded-For`, or a similar header
- WHEN the request reaches an administrative route
- THEN the request remains rejected
- AND the header values are not logged or reflected as authorization evidence

#### Scenario: Public routes retain their existing access behavior

- GIVEN requests to `/health`, `/chat`, `/chat/stream`, `/preguntar`, or dashboard routes
- WHEN those requests are made from a non-loopback peer
- THEN this administrative guard does not change their existing route behavior

#### Scenario: Offline boundary verification uses no external service

- GIVEN a FastAPI test client and a deterministic request-peer configuration
- WHEN protected and unchanged routes are exercised
- THEN the tests prove accepted and rejected outcomes without live authentication, browser, network, or paid-service calls

### Requirement: Bounded uploads return 413 without retained history or partial artifacts

The upload interfaces `/normalizador/empleabilidad` and `/normalizador/silabos` SHALL reject a request with HTTP `413` when its raw upload exceeds the configured byte limit or its ZIP expansion exceeds the configured archive limits. When trustworthy length metadata proves that the request is too large, rejection SHALL occur before an execution-history record or execution directory is created. When metadata is absent, false, or incomplete, streaming enforcement SHALL stop at the configured boundary without retaining the oversized payload. Every partial file, temporary upload, and execution directory created while handling the rejected request SHALL be removed. Upload handling SHALL remain bounded and SHALL NOT require loading the complete request into memory.

#### Scenario: Trustworthy oversized length is rejected before allocation

- GIVEN an upload request whose trustworthy length exceeds the configured raw-byte limit
- WHEN it is submitted to either normalizer upload endpoint
- THEN the endpoint returns HTTP `413`
- AND no execution-history record is created
- AND no execution directory or retained upload is created

#### Scenario: Oversized stream is rejected without trustworthy metadata

- GIVEN an upload whose length metadata is absent or claims an acceptable size
- WHEN the streamed bytes cross the configured limit
- THEN the endpoint returns HTTP `413`
- AND reading stops at the rejection boundary rather than accepting the full payload
- AND no execution-history record or partial artifact remains

#### Scenario: ZIP expansion limit is enforced privately

- GIVEN a raw upload within the outer byte limit whose ZIP entries exceed the configured expanded-entry or expanded-size limit
- WHEN the syllabus upload is validated
- THEN the endpoint returns HTTP `413`
- AND the raw archive, extracted files, execution history, and partial execution directory are not retained

#### Scenario: Valid bounded upload preserves existing acceptance

- GIVEN an upload within all configured raw and ZIP limits
- WHEN it is submitted through the public upload endpoint
- THEN the existing accepted-upload response and subsequent execution behavior remain available
- AND the upload is not read as one unbounded in-memory value

#### Scenario: Offline stream verification uses small deterministic fakes

- GIVEN a bounded byte stream or `BytesIO` fake and a temporary directory
- WHEN boundary, missing-metadata, lying-metadata, and ZIP-limit cases are exercised
- THEN tests observe `413`, cleanup, and history behavior without large fixtures, external calls, or live workers

### Requirement: Finalized executions retain a private stable syllabus source for import

The normalizer SHALL preserve or materialize exactly the minimal syllabus source required by the importer when a syllabus execution is finalized. The stable source SHALL remain available to preview and import operations after disposable staging cleanup, SHALL not expose bulky staging data, and SHALL be excluded from public output downloads. Historical executions that lack the stable source SHALL remain readable when their legacy `limpios/silabos.jsonl` source is present. A finalized execution without an available valid source SHALL not be presented as importable.

#### Scenario: Finalization preserves the importer source

- GIVEN a syllabus execution with a valid normalized syllabus source and disposable staging siblings
- WHEN the execution reaches finalization
- THEN the minimal importer-owned source remains available for later import operations
- AND unrelated bulky staging artifacts may be removed

#### Scenario: Preview and import load the stable source after cleanup

- GIVEN a finalized syllabus execution whose staging directory has been cleaned
- WHEN the public Neo4j preview or import seam loads that execution
- THEN it can read the preserved source and produce the normal preview or import eligibility result
- AND it does not require discarded staging files

#### Scenario: Stable source is private

- GIVEN a finalized execution with an importer-owned syllabus source
- WHEN a caller requests public execution outputs
- THEN the source is not included as a downloadable public output
- AND no unrelated staging artifact becomes downloadable because the source was preserved

#### Scenario: Historical legacy source remains compatible

- GIVEN a historical execution with no importer-owned stable source but with `limpios/silabos.jsonl`
- WHEN preview or import loading is requested
- THEN the legacy source can be used as a compatibility fallback
- AND the execution remains subject to all current publication and validation gates

#### Scenario: Missing or invalid source blocks importability

- GIVEN a finalized execution with neither a valid stable source nor a valid legacy source
- WHEN preview or import eligibility is requested
- THEN the operation reports an unavailable source
- AND it does not claim that the execution is importable or publishable

#### Scenario: Offline artifact verification uses fixtures only

- GIVEN temporary execution fixtures representing finalized, legacy, cleaned, and missing-source cases
- WHEN importer loading and output filtering are exercised
- THEN tests verify source retention and privacy without a live Neo4j connection or external call

### Requirement: Initialization deletes stale non-terminal executions without live workers

Under the documented single-instance manager contract, manager initialization SHALL delete persisted non-terminal executions for which no live in-process worker exists. It SHALL preserve terminal executions and their readable reports. It SHALL NOT attempt to resume arbitrary work after restart. The operator documentation SHALL state that multiple workers sharing one data directory are unsupported and that this cleanup rule is not safe as a multi-process coordination mechanism.

#### Scenario: Stale non-terminal execution is deleted at initialization

- GIVEN a persisted execution in a non-terminal state and no live worker in the newly initialized manager
- WHEN the manager initializes
- THEN the persisted execution is removed from the manager's available history
- AND it is not presented as resumable or cancellable work

#### Scenario: Terminal history survives initialization

- GIVEN persisted executions in terminal states with readable reports
- WHEN the manager initializes
- THEN terminal history and its reports remain available with their prior content

#### Scenario: No arbitrary restart resume occurs

- GIVEN a persisted execution that was non-terminal when the previous process stopped
- WHEN a new manager initializes
- THEN no worker is started to resume that execution
- AND the system reports only the documented cleanup outcome

#### Scenario: Single-instance contract is explicit

- GIVEN an operator considers sharing the data directory across multiple workers or processes
- WHEN the deployment documentation is consulted
- THEN it states that the deployment is unsupported for this cleanup contract
- AND the system does not claim that initialization can distinguish another process's live worker

#### Scenario: Offline manifest verification is deterministic

- GIVEN a temporary directory containing terminal and non-terminal manifests
- WHEN a new manager is initialized without starting workers
- THEN tests observe stale-manifest deletion and terminal-history preservation using local filesystem fixtures only

### Requirement: HITL mutations are lock-before-snapshot atomic operations

The human-in-the-loop decision seam SHALL validate the target execution directory before mutation and SHALL acquire the existing mutation lock before capturing any transactional snapshot. Mutation, rollback, and atomic file replacement SHALL remain within the lock-protected critical section. A failed mutation SHALL restore only the state observed for that locked operation and SHALL NOT undo a successful concurrent mutation. Existing test-hook seams SHALL remain usable without introducing a competing lock hierarchy.

#### Scenario: Snapshot follows validation and lock acquisition

- GIVEN a valid target directory and a pending decision mutation
- WHEN the decision operation begins
- THEN target validation occurs before mutation
- AND the mutation lock is acquired before the snapshot is captured
- AND the snapshot precedes any mutation

#### Scenario: Failed mutation rolls back its locked operation

- GIVEN a decision mutation that fails after its locked snapshot is captured
- WHEN rollback runs
- THEN the files covered by that operation return to their pre-mutation state
- AND atomic file replacement is not exposed as a partially written state

#### Scenario: Concurrent success is not undone by a stale rollback

- GIVEN two overlapping decision attempts against the same execution
- WHEN one attempt successfully commits while the other fails
- THEN the failing attempt cannot restore a snapshot captured before the successful mutation
- AND the successful mutation remains observable

#### Scenario: Offline hook ordering proves the public transaction contract

- GIVEN deterministic fake hooks for validation, lock entry, snapshot, mutation, and rollback
- WHEN success and failure paths are exercised
- THEN tests observe validation → lock → snapshot → mutation ordering and protected rollback behavior without threads, external services, or live data

### Requirement: Aggregate LLM batch failures block publication and import

The curricular analysis seam SHALL expose an aggregate failure whenever any batch invocation fails, returns an unusable response, or leaves required source coverage incomplete. Successful and failed batch evidence SHALL remain available for audit. An aggregate failure SHALL prevent the execution from being treated as successfully completed, SHALL block publication, and SHALL block Neo4j import eligibility. Human-review handling MAY remain non-fatal only when every source logro has valid coverage and no batch invocation or response failure occurred. Offline mode SHALL remain deterministic, and this change SHALL NOT modify the curricular analyst prompt.

#### Scenario: One failed batch blocks an otherwise partial success

- GIVEN a curricular analysis with at least one successful batch and one failed batch
- WHEN the analysis result reaches cleanup or release evaluation
- THEN the result exposes an aggregate failure
- AND successful and failed audit evidence remains readable
- AND publication and Neo4j import eligibility are blocked

#### Scenario: Invalid or incomplete response is not successful coverage

- GIVEN a batch response that is unusable or leaves a source logro without valid coverage
- WHEN the complete curricular analysis is finalized
- THEN the analysis is marked incomplete or failed
- AND it cannot be represented as a successful public completion
- AND its available audit evidence is retained

#### Scenario: Valid human review remains non-fatal only with complete coverage

- GIVEN every source logro has valid coverage, no batch invocation or response failed, and some decisions require human review
- WHEN the release gate evaluates the analysis
- THEN human-review findings remain non-fatal according to the existing policy
- AND the execution remains subject to the existing human approval requirements

#### Scenario: Failed analysis is not importable through the public seam

- GIVEN an execution with an aggregate curricular analysis failure
- WHEN a Neo4j preview or import eligibility operation is requested
- THEN it reports the blocked semantic-analysis state
- AND it does not publish or import partial semantic results

#### Scenario: Offline fake LLM verification is deterministic

- GIVEN a fake LLM that succeeds for one batch and fails for another, plus deterministic structured responses
- WHEN analysis and release-gate behavior are exercised
- THEN tests observe aggregate failure, retained evidence, and blocked publication without live LLM, LangSmith, or paid API calls

### Requirement: Neo4j graph and local history reconcile deterministically

The import workflow SHALL treat Neo4j graph durability and local import history durability as separate domains and SHALL NOT claim cross-system atomicity. It SHALL record sufficient local import intent and lineage for a deterministic outcome when graph work and local history completion are interrupted. It SHALL reconcile graph-tagged imports that committed before local completion became durable, using explicit outcomes rather than false success. Local history replacement SHALL be atomic at its public durability seam. Neo4j transaction callbacks SHALL remain safe to retry, and existing pre-commit failure handling SHALL remain intact.

#### Scenario: Successful graph commit followed by local-history failure is recoverable

- GIVEN an import whose graph transaction commits and whose local completion update fails or is interrupted
- WHEN the import history is later reconciled
- THEN graph evidence and recorded lineage produce an explicit recoverable outcome
- AND the system does not silently report ordinary completion without durable local history

#### Scenario: Graph evidence is absent for an interrupted import

- GIVEN an `en_progreso` import with no matching committed graph evidence
- WHEN reconciliation runs
- THEN it produces an explicit failed or indeterminate outcome appropriate to the available intent
- AND it does not claim that the import committed

#### Scenario: Local history replacement is atomic and readable

- GIVEN a valid history transition to a new import outcome
- WHEN the local history is replaced
- THEN readers observe either the previous complete history or the new complete history
- AND never a partially written history document

#### Scenario: Pre-commit failure preserves existing failure semantics

- GIVEN the graph transaction fails before commit
- WHEN the import operation reports its outcome
- THEN the existing failed-import behavior remains observable
- AND no graph-committed recovery outcome is claimed

#### Scenario: Retried transaction callback does not duplicate import effects

- GIVEN the Neo4j driver invokes the import transaction callback more than once for a retryable condition
- WHEN the callback completes
- THEN the resulting graph state and lineage are equivalent to one successful application
- AND local history reconciliation can identify the same import deterministically

#### Scenario: Offline fake-driver verification covers ambiguity

- GIVEN fake Neo4j sessions, transactions, graph tags, local history, and injected local-write failures
- WHEN committed, failed, interrupted, and retried paths are exercised
- THEN tests verify explicit reconciliation and atomic history outcomes without connecting to Neo4j or any external service

### Requirement: Relationship-safe rollback preserves later and legacy ownership

The revert seam SHALL delete an imported relationship only when it is safe to remove: the relationship must be attributable to the reverted import and no surviving later import, imported node, or coverage dependency may still require the semantic edge. Relationships that predate imports or have no import-created attribution SHALL never be deleted by reverting an import. The seam SHALL support legacy scalar `_ciar_import_id` metadata and any selected future-compatible multi-owner representation without requiring destructive migration.

#### Scenario: Reverting an earlier import preserves a shared later dependency

- GIVEN an earlier import created or attributed a relationship and a later non-reverted import relies on the same semantic edge
- WHEN the earlier import is reverted
- THEN the shared relationship remains available to the later import
- AND only relationships proven unnecessary for surviving data may be removed

#### Scenario: Legacy scalar ownership remains readable

- GIVEN an existing relationship with scalar `_ciar_import_id` metadata
- WHEN its owning import is reverted
- THEN rollback evaluates the legacy metadata and dependency state correctly
- AND does not require rewriting all existing graph metadata before safe behavior is available

#### Scenario: Multi-owner attribution removes only the reverted ownership

- GIVEN a relationship represented with multiple import owners and one owner is reverted
- WHEN rollback evaluates that relationship
- THEN the reverted ownership is removed from consideration
- AND the relationship remains while another surviving owner or dependency requires it
- AND it may be deleted only after no surviving ownership or dependency remains

#### Scenario: Untagged domain relationship is preserved

- GIVEN a relationship with no import-created attribution
- WHEN any import is reverted
- THEN that relationship is not deleted
- AND unrelated domain graph structure remains unchanged

#### Scenario: Offline fake-graph verification observes safe deletion

- GIVEN a fake graph containing shared edges, legacy scalar tags, future-compatible ownership, untagged edges, and later coverage dependencies
- WHEN revert queries or graph effects are exercised
- THEN tests verify preserved shared and untagged relationships and removal only of safe imported relationships without a live Neo4j connection
