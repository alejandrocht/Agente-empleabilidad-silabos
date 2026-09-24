# Recover blocked syllabus CSV downloads

## Goal

Expose already-materialized syllabus CSVs for inspection/download even when the release gate blocks import, including archived executions such as `NOR_6c47107833b241ff` on another Windows host. Never represent these files as importable or fabricate a missing syllabus.

## Evidence

- The Windows execution has `hitl=0`, `estado=no_publicado`, `release_gate.decision=BLOCK_IMPORT`, with `TECHNICAL_ANALYSIS_INCOMPLETE` and `UNLINKED_SOURCE_OUTCOME`.
- Six canonical CSV files exist under `salidas/`; `limpios/silabos.jsonl` has 74 records and `entrada/cactus.zip` exists. The expected 75th syllabus is not yet identified.
- The API currently filters blocked CSVs from `outputs` and denies their download, despite the inspection UI already handling declared CSVs with a blocked-gate warning.

## Allowed edit surfaces

- `backend/agente/normalizador/persistencia_ejecuciones.py`
- `backend/agente/api/normalizador.py`
- `backend/tests/unit/test_normalizador_api.py`
- `frontend/src/components/InspeccionEjecucionNormalizador.jsx`
- `frontend/src/components/InspeccionEjecucionNormalizador.test.jsx`

## Tasks

- [x] Locate generation and publication boundaries, and establish recoverability from Windows metadata.
- [x] Add a regression for blocked archived CSVs: `outputs` remains empty, only existing canonical files appear in `draft_outputs`, and only those files can be downloaded. RED: backend `KeyError: 'draft_outputs'`; frontend warning absent.
- [x] Reconcile draft CSV metadata from disk and authorize narrowly scoped draft downloads without changing `BLOCK_IMPORT`.
- [x] Display draft CSVs in inspection with a clear not-importable warning and focused UI regression.
- [ ] Verify deployment on the Windows host and obtain the Cactus source report to explain 75 expected versus 74 processed. Local focused tests: backend 3 passed (18 deselected); frontend 42 passed; scoped diff --check passed. Independent verifier repeated both, then ran the broader backend API/execution suite (40 passed) and a successful Next.js production build. The combined `fixesfront` changes plus draft UI passed 12 frontend suites/97 tests and another Next.js build. Native review inspect could not isolate this candidate from unrelated dirty paths; no lineage started. The code has not been deployed to the Windows host. Frontend work-unit commit: `38cc12e` (`fix(frontend): centralize normalizer run status`).

## Constraints

- Do not edit or rerun the user's Windows execution; do not change the release gate or import eligibility.
- Keep staging data and unrelated existing changes untouched. The user later authorized a selective push to `test/local-llm-technical-pipeline` including the `fixesfront` session; this supersedes the earlier no-push instruction for this exact scope only.
- Engram mirror pending: local memory provider currently cannot initialize.
