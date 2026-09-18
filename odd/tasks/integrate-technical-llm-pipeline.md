# Integrate Technical LLM Pipeline

## Objective

Make the post-extraction curriculum pipeline the single source of truth: DOCX/PDF extraction runs once, deterministic outputs are generated from those records, and the technical-only LLM analysis consumes the same records in the same execution.

## Problem

The repository currently contains an active legacy LLM/output path and a separate technical harness/output path. The duplication is at the orchestration and output-contract level, not a second DOCX/PDF parse. Removing modules before routing and compatibility checks could break the API, approvals, tests, or Neo4j import flow.

## Why

Avoid repeated parsing and divergent data, make the technical-only behavior the production path, preserve literal evidence and Python-owned IDs/relationships, and delete only modules proven to have no remaining callers or contract role.

## Scope

- Reuse the `registros` produced by `limpieza.py` and the DOCX/PDF adapters.
- Run `analista_tecnico.py` from the production execution after extraction.
- Make the technical curricular graph canonical: `Curso → Sílabo → Logro → Competencia técnica → Cobertura`.
- Preserve deterministic CSV generation and pending technical proposals.
- Keep human approval as the gate before materializing technical proposals in Neo4j.
- Replace the legacy CHH approval, output, and importer paths before deleting their retired modules.
- Keep DOCX and PDF parsers separate; extract only genuinely shared helpers.

## Constraints

- Do not parse DOCX/PDF twice.
- Technical prompts contain only career, course, achievements, and filtered technical catalog entries.
- Evidence must be literal and come from achievements in the same syllabus.
- Python owns `CUR_`, `SIL_`, `COMP_`, `LOGRO_`, and `COB_CUR_` IDs and all relationships.
- New proposals remain `PENDIENTE_APROBACION`; no unapproved proposal reaches Neo4j.
- Do not include `backend/.env`, API keys, generated outputs, or unrelated pre-existing changes.
- Do not delete a module solely because it appears redundant; prove callers, entrypoints, tests, and compatibility status first.

## Checklist

- [x] T1. Map the production execution and output contracts; record exact callers and compatibility constraints.
- [x] T2. Wire the technical analyzer into the one-pass production execution while reusing extracted records.
- [x] T3. Add/update focused tests for one extraction pass, technical proposals, pending approval, and API compatibility.
- [x] T4. Migrate approved technical proposals and Neo4j integration without bypassing approval gates.
  - [x] T4.0. Allow technical deterministic output with the LLM explicitly disabled.
  - [x] T4.1. Make the technical catalog the canonical production output and block publication while technical proposals await review.
  - [x] T4.2. Replace the CHH pending/decision transaction with a technical row approval journal and approved-only catalog rebuild.
  - [x] T4.3. Move the existing Neo4j facade safeguards onto the technical graph writer: preview, fingerprint, confirmation, history, and reversion.
  - [x] T4.4. Make execution reports/download filtering and frontend inspection contract-aware for the technical graph.
  - [x] T4.5. Complete the technical LLM production contract.
    - [x] T4.5a. Translate the technical system prompt to English while preserving literal-evidence and catalog constraints.
    - [x] T4.5b. Load the real technical catalog with exact career matching; do not introduce career aliases.
    - [x] T4.5c. Reject an LLM-analyzed syllabus when no technically evidenced proposal survives validation.
    - [x] T4.5d. Remove `contenido_semanal.csv` and its Neo4j model from the published technical contract.
    - [x] T4.5e. Resolve strict Mypy errors in the active transitive curriculum graph and run real LLM/Neo4j smoke checks when their external services are available. *(services unavailable; probes recorded)*
- [x] T4.6. Keep the local and hosted technical analyzers ready behind one provider switch.
  - [x] T4.6a. Resolve provider-specific analyst models: Ollama `qwen3:27b` and OpenAI `gpt-5.6-luna`.
  - [x] T4.6b. Verify the frontend career labels match the canonical XLSX exactly, without aliases.
  - [x] T4.6c. Verify both provider configurations and the frontend submission contract.
- [x] T4.7. Make the technical XLSX a repository-owned, technical-only curriculum contract.
  - [x] T4.7a. Copy the canonical 277-row XLSX into the backend catalog directory.
  - [x] T4.7b. Remove the `legacy|technical` configuration choice and default every curriculum execution to the repository XLSX.
  - [x] T4.7c. Verify the canonical XLSX, configuration snapshot, and technical execution path.
- [ ] T5. Re-audit every normalizer module and remove only proven dead/retired curriculum modules; keep employability CHH and a deletion ledger.
  - [ ] T5a. Remove runtime/API/persistence/Neo4j mode branches and make the technical contract unconditional for syllabus executions.
  - [ ] T5b. Remove legacy curricular analyzer/output/approval seams proven unreachable after T5a.
  - [ ] T5c. Record every deleted test/module with caller evidence; preserve shared extraction and employability CHH.
- [ ] T6. Run focused verification, Ruff/LSP checks, and the complete suite; record known unrelated failures honestly.

## Acceptance Criteria

1. A DOCX/PDF execution extracts each syllabus once and feeds the same normalized records to deterministic outputs and the technical LLM stage.
2. The production path emits deterministic catalogs plus reviewable technical proposals without sending period, sumilla, weekly program, or non-technical skills/tools to the technical model.
3. No pending proposal can be materialized into Neo4j without explicit approval.
4. Existing API contracts and active approval/import flows remain covered or are intentionally migrated with tests.
5. Any deleted file has a recorded evidence-based reason and no remaining production/test/entrypoint references.
6. Verification results identify passed, failed, skipped, and unavailable checks.

## T1 Findings

- Production parses each accepted syllabus exactly once in `limpieza.py` through the separate DOCX/PDF adapters and passes the in-memory `registros` to downstream stages.
- The technical harness does not reparse documents; it consumes serialized JSONL, but it is not connected to the API.
- The safe integration seam is after extraction in `limpieza.py`, calling `analista_tecnico.inferir_competencias_tecnicas(registros, ...)` directly rather than invoking the CLI harness.
- Technical proposals do not match the current approval transaction shape, and `neo4j_catalogos.py` lacks the existing release-gate, preview, confirmation, history, and reversion behavior.
- `analista_llm.py`, `salida.py`, approval modules, and the current Neo4j facade have production and test callers. No normalizer module is immediately safe to delete.
- The technical catalog path and lifecycle must be added to production configuration before wiring the analyzer.

## T2 Findings

- Added explicit `legacy`/`technical` analyzer mode and technical catalog path to the immutable curricular configuration snapshot.
- Technical mode calls `analista_tecnico.inferir_competencias_tecnicas` directly with the already extracted in-memory `registros`; it never invokes `harness_tecnico.py`, the legacy analyst, or embeddings.
- Technical proposals and a completion/fallback audit are persisted under `salidas/reportes/`, while deterministic `salida.py` output and its release gate remain unchanged for the compatibility phase.
- The technical branch is gated by both `usar_llm=True` and `modo_analista="technical"`; cancellation still propagates.

## T3 Findings

- Added configuration tests for technical mode, required catalog path, and immutable snapshot values.
- Added routing tests proving one DOCX extraction feeds both deterministic output and technical inference by object identity, while the legacy analyzer is not called.
- Added failure-path coverage proving technical analyzer failure emits a warning/report and preserves deterministic CSV output.
- Existing API and approval tests remain unchanged and continue to cover the legacy contract while T4 adds the technical proposal adapter.

## T4 Design Findings

- The existing pending/decision HTTP endpoints can project technical proposals as rows without an HTTP breaking change, but the legacy CHH approval mutation cannot consume them.
- The required adapter must journal explicit `ADD`, `DISCARD`, and `KEEP_PENDING` decisions; rebuild catalogs using only approved rows; preserve pending and discarded rows as audit evidence.
- `salida_catalogos.py` currently accepts a missing approval state, so its internal contract must be tightened to require `APROBADA`.
- `neo4j_catalogos.py` lacks the existing importer facade safeguards: preview, fingerprint confirmation, history, and reversible create markers. It cannot be connected to production unchanged.
- User selected the technical syllabus/logro/coverage graph as canonical and explicitly authorized retirement of the CHH flow after equivalent safeguards are implemented and verified. Technical review permits `ADD`, `DISCARD`, and `KEEP_PENDING`. No source module is safe to delete before its replacement passes callers, tests, and import-safety checks.

## T4.0 Findings

- Technical mode is now selected by the immutable analyst-mode snapshot, independently of `usar_llm`.
- With `usar_llm=False`, it bypasses CHH loading and all LLM construction/inference, emits zero proposals, writes the five-file contract, and records `DETERMINISTICO_SIN_LLM`.
- A clean deterministic technical run over `Silabos_train` processed 21/21 real DOCX/PDF files and produced an `ALLOW_IMPORT` gate. The Word lock file prefixed `~$` was excluded from packaging as a non-syllabus temporary artifact.

## T4.1 Findings

- In technical mode, `limpieza.py` now bypasses both legacy CHH catalog loading and `salida.py`; the same extracted records produce the five canonical technical CSVs.
- The technical release gate blocks import while proposals remain pending and also records deterministic-output and analyzer status.
- The catalog builder now rejects every technical proposal whose approval state is not exactly `APROBADA`, including a missing state.
- A technical analyzer failure still emits all six deterministic CSVs and a blocked release gate.

## T4.2 Findings

- Existing pending routes now dispatch technical mode by immutable manifest snapshot and expose technical rows without synthesizing CHH packages or identities.
- The technical decision journal is append-only and idempotent; it accepts `ADD`, `DISCARD`, and `KEEP_PENDING` only for source proposal IDs.
- Only journaled `ADD` records enter catalog rebuilding; the source proposal JSONL remains unchanged, while discarded and pending decisions stay audit-visible.
- Terminal technical executions preserve `limpios/silabos.jsonl`, so rebuilds reuse normalized records instead of reparsing source files.

## T4.4 Preflight Findings

- Strict Mypy currently reports 98 inherited errors across 14 modules because the technical cleanup module still imports legacy `salida.py`, which in turn pulls the CHH package/resolution/persistence tree.
- The first safe correction is a technical-only import/output/persistence seam; it must preserve the legacy branch until UI and persisted manifests understand both contracts.

## T4.3 Findings

- `ImportadorNeo4j` preserves its preview, fingerprint confirmation, local history, and reversion facade while selecting technical input from the immutable manifest mode.
- Technical preflight accepts only an allowed release gate and the five canonical CSV files; it does not load CHH catalogs or proposal artifacts.
- Technical Cypher uses `ON CREATE` markers for every newly created node and relationship and rejects non-null property conflicts before writing.
- Reversion removes only relationships/nodes tagged with the import ID, retaining pre-existing or subsequently connected graph data.

## T4.5 Partial Findings

- `SYSTEM_PROMPT_TECNICO` is now English and preserves its existing constraints: literal learning-outcome evidence only, candidate catalog as non-factual context, no confidence/chain-of-thought/invented tools/graph identifiers, exact catalog references, and human review for new competencies.
- The active strict Mypy graph is clean without `type: ignore`: PDF geometry cells now have an explicit typed shape, optional cache/package identities are narrowed before use, compatibility facades explicitly re-export their legacy symbols, and strict tests annotate callbacks/progress collections.
- The loader now accepts the real UTF-8/BOM CSV schema, expands semicolon-separated `carreras_origen`, and compares the execution career to each catalog career token exactly after whitespace cleanup only. It does not map `INGENIERIA_DE_SISTEMAS` to `SISTEMAS` or apply any other alias. The real catalog loads 612 source rows into 742 career associations; exact `SISTEMAS` selects 60 candidates and the alias selects zero.
- Each LLM-analyzed syllabus must now produce at least one proposal that survives catalog-reference, specific-learning-outcome, and literal-evidence validation. Empty or entirely invalid responses raise an explicit syllabus-scoped error; the production boundary also rejects an empty analyzer result, records deterministic fallback, and blocks release instead of silently publishing zero proposals.
- The published technical contract now contains five CSVs: course, syllabus, competencies, learning outcomes, and coverage. The builder no longer writes `contenido_semanal.csv`; persistence/frontend contracts no longer expose it; the technical Neo4j reader, comparison, preview, summary, and writer no longer model `ContenidoSemanal` or `TIENE_CONTENIDO`. Existing generated output directories were preserved as historical artifacts.
- Focused analyzer test passed: `PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_analista_tecnico.py -q` → 8 passed (one third-party deprecation warning); parent active LSP was clean. An independent read-only review found no functional defect and noted only that the regression test intentionally covers the core literal-evidence/catalog rules rather than every prompt clause.

## T4.4 Findings

- Technical execution now has a neutral output contract. Its runtime path lazy-loads neither legacy CHH catalog/output/approval modules nor embeddings; the legacy path remains intact.
- Persistence, API report/download filtering, and Neo4j routing select their behavior from the immutable `modo_analista` snapshot. A permitted technical release gate exposes precisely the five declared CSVs; a blocked gate exposes audit artifacts only.
- The frontend recognizes both contracts. Technical inspection previews all five declared CSVs, derives technical counts, bypasses the CHH approval panel, and exposes Neo4j only after `ALLOW_IMPORT`, a complete five-file contract, and successful previews. Legacy conditions are unchanged.

## Verification Evidence

- Read-only mapper inspected API, execution manager, extraction adapters, legacy and technical analyzers, output builders, approvals, Neo4j importers, and frontend assumptions.
- Mapper identified exact callers, compatibility gaps, deletion candidates, and tests to update; no source files were changed by the mapper.
- Focused command: `cd 'Agente-empleabilidad-silabos/backend' && .venv/bin/python -m pytest tests/unit/test_configuracion_normalizador_curricular.py tests/unit/test_normalizador_silabos.py -q` → 53 passed.
- LSP diagnostics for `settings.py`, `limpieza.py`, `salida_catalogos.py`, and updated tests → clean; intentional Spanish-domain vocabulary is allowlisted in `_typos.toml` and scoped spellchecker markers.
- Focused technical-output command: `cd 'Agente-empleabilidad-silabos/backend' && .venv/bin/python -m pytest tests/unit/test_salida_catalogos.py tests/unit/test_normalizador_silabos.py -q` → 42 passed.
- Focused technical-approval command: `cd 'Agente-empleabilidad-silabos/backend' && .venv/bin/python -m pytest tests/unit/test_normalizador_aprobaciones.py tests/unit/test_normalizador_api.py tests/unit/test_salida_catalogos.py -q` → 89 passed.
- Focused technical-Neo4j command: `cd 'Agente-empleabilidad-silabos/backend' && .venv/bin/python -m pytest tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py -q` → 30 passed; LSP is clean for the technical writer, facade, and facade tests.
- Focused technical deterministic command: `cd 'Agente-empleabilidad-silabos/backend' && .venv/bin/python -m pytest tests/unit/test_configuracion_normalizador_curricular.py tests/unit/test_normalizador_silabos.py tests/unit/test_salida_catalogos.py -q` → 61 passed; LSP is clean for the changed router and tests.
- T4.4 backend focused pytest → 71 passed.
- T4.5 strict Mypy command: `cd backend && .venv/bin/python -m mypy agente/normalizador/silabos/aprobaciones_tecnicas.py tests/unit/test_configuracion_normalizador_curricular.py tests/unit/test_normalizador_silabos.py --show-error-codes --no-error-summary` → clean, zero findings, with no new typing ignores.
- T4.5 catalog/empty-proposal command: `PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_analista_tecnico.py tests/unit/test_normalizador_silabos.py::test_technical_analyzer_without_valid_proposals_blocks_release -q` → 11 passed; the real CSV smoke loaded 612 source rows, 742 exact career associations, 60 `SISTEMAS` candidates, and zero `INGENIERIA_DE_SISTEMAS` alias matches.
- T4.5 five-file backend command: `PYTHONPATH=. ../.venv/bin/pytest tests/unit/test_salida_catalogos.py tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_silabos.py tests/unit/test_normalizador_ejecuciones.py -q` → 90 passed.
- T4.5 five-file frontend command: `npm test -- src/components/NormalizadorPanel.test.jsx src/components/InspeccionEjecucionNormalizador.test.jsx src/components/Neo4jImportPanel.test.jsx` → 28 passed.
- Final focused backend command across analyzer, five-file builder, Neo4j writer/facade, production routing, and persistence → 100 passed with two third-party deprecation warnings.
- Focused Ruff passed; strict Mypy passed with no output; `git diff --check` passed. Active LSP confirmed 23 Python files clean; five JavaScript files were inconclusive because their server is push-only, and `npm run build` independently compiled and type-checked successfully.
- External smoke probes: Ollama `127.0.0.1:11434` refused the connection; Neo4j Bolt `127.0.0.1:7687` and HTTP `127.0.0.1:7474` were closed. Real LLM and live Neo4j writes were therefore unavailable and were not simulated as successful.
- Native review inspection selected only the intended T4.5 untracked files, then stopped at `managed_assets_outdated`. The exact provider sync command failed because RTK has no selected supported detected agent, so no review lineage was created and no review verdict was claimed.
- T4.4 frontend focused command: `cd frontend && npm test -- src/components/NormalizadorPanel.test.jsx src/components/InspeccionEjecucionNormalizador.test.jsx src/components/Neo4jImportPanel.test.jsx` → 28 passed. Ruff on the focused backend files passed; parent active LSP diagnostics are clean for `persistencia_ejecuciones.py` and `test_normalizador_ejecuciones.py`.
- Native review preflight was attempted. It excluded unrelated untracked artifacts, then stopped at `managed_assets_outdated`; its provider-issued sync command failed because RTK has no selected supported agent. No review lineage was created and no delivery action was attempted.

## Progress

- Current decision: replace the CHH pipeline with the technical curricular graph, then delete the retired path only after equivalent safeguards are verified.
- T1–T4.7 are complete. T5 is active; T6 remains pending.
- The canonical source catalog was `/Users/alejandromcht/Downloads/catalogo_competencias_tecnicas.xlsx` and is now vendored at `backend/catalogos/catalogo_competencias_tecnicas.xlsx` with the same SHA-256. It contains sheet `Catalogo`, exact columns `Carrera`, `Habilidad tecnica`, `Descripcion`, 277 rows, and 14 exact frontend career labels; it supersedes the previously inspected CSV.
- Curriculum runtime now ignores the retired `NORMALIZADOR_CURRICULAR_ANALYST_MODE` and external catalog-path settings, always snapshots `modo_analista=technical`, and resolves the vendored XLSX from `BASE_DIR`. T4.7 verification: 80 focused tests passed; focused Ruff, strict Mypy, diff check, and LSP passed; the runtime smoke loaded 277 rows and 26 exact `Ingeniería de Sistemas` candidates.
- T4.7 deletion ledger: removed three legacy-only LLM tests that intentionally exercised the retired CHH analyzer and became invalid once the only runtime mode became technical. The remaining legacy branches are now being removed under T5; employability CHH remains out of scope.
- T4.6 selected models: Ollama `qwen3:27b`; OpenAI `gpt-5.6-luna`. Both are now resolved independently, with `NORMALIZADOR_CURRICULAR_LLM_PROVIDER` as the only provider switch; Ollama also owns its provider-specific local base URL.
- T4.6a verification: provider/configuration and technical-analyzer tests → 30 passed; focused Ruff and strict Mypy passed; diff check passed; LSP reported only pre-existing Spanish spellchecker informational notices.
- T4.6a native review inspection selected the two relevant untracked files, but the selection operation failed with native `schema-incompatible`; no lineage was created and no review verdict is claimed.
- Current branch: `test/local-llm-technical-harness`.
- Working tree contains substantial pre-existing and unrelated changes; preserve them.

## Next Step

Complete T4.7 by vendoring the canonical XLSX and making technical analysis the only curricular configuration. Then start T5 with a fresh caller/entrypoint audit before deleting dead curriculum-only CHH modules; preserve employability CHH. Run the broader T6 suite afterward and repeat live Ollama/Neo4j smoke checks when those services are available.
