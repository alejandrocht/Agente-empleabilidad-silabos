# Integrate Career-Scoped Competency Catalog

## Objective

Use the official career-to-skill CSV as the production candidate assignment source, preserving official `id_habilidad` values and exact career associations while reusing the repository XLSX descriptions.

## Problem and rationale

The current production setting points at `catalogo_competencias_tecnicas.xlsx`, which has career/name/description but no official skill IDs. The new CSV has career and skill IDs/names but no descriptions. Read-only comparison found an exact one-to-one match between all 277 career/name pairs in the new CSV and the existing XLSX, so no description needs to be invented or separately vendored.

## Source evidence

- User source: `/Users/alejandromcht/Downloads/carrera_competencia_oficial.csv`; SHA-256 `126759c62272623a95f3652ab8139d034fe4b13b1ae66b241044110e4da33b84`.
- New CSV schema: `id_carrera,nombre_carrera,id_habilidad,nombre_habilidad`; 277 rows, 14 careers, 222 distinct skills, no duplicate career-skill pairs or conflicting IDs/names.
- Existing description source: `backend/catalogos/catalogo_competencias_tecnicas.xlsx`; all 277 `(Carrera, Habilidad tecnica)` pairs match the new CSV exactly.
- Career labels were verified to match the frontend's canonical career choices.

## Scope and constraints

- Vendor only `carrera_competencia_oficial.csv`; reuse the existing XLSX for descriptions.
- Add a narrow `.gitignore` exception for the vendor CSV so it is tracked; preserve the global `*.csv` ignore rule and all existing ignore exceptions.
- Configure production to load the new mapping CSV and join descriptions by normalized `(nombre_carrera, nombre_habilidad)`.
- Preserve `id_habilidad` as the candidate `catalogo_ref`; keep Python responsible for graph IDs and relationships.
- Bind catalog provenance/hash to both the mapping CSV and XLSX description source.
- Preserve old XLSX and legacy CSV loader compatibility; no fuzzy matching, embeddings, new dependencies, prompt shortlist, or output-schema changes.
- Preserve unrelated pre-existing worktree changes. No commit unless explicitly requested.

## Tasks

- [x] T1. Add the official CSV and implement strict career/skill/description joining with source-ID preservation; write failing loader tests first, then implement and triangulate.
- [x] T2. Switch the production configuration to the new CSV, update repository-catalog/config tests and backend README, then run focused verification.

## Acceptance criteria

1. Production catalog loads all 277 official career-skill assignments across 14 careers, and the vendor CSV is not ignored by Git.
2. Each candidate has the source `id_habilidad`, exact career label, official skill name, and existing XLSX description.
3. Missing or ambiguous description joins and duplicate/conflicting source mappings fail closed with useful row diagnostics.
4. Prompt/materialization reference validation continues to work using official source IDs; graph IDs and CSV schemas remain Python-owned and unchanged.
5. Existing XLSX/legacy CSV loader tests remain valid.

## Routing, TDD, and delivery

- Route: delegated direct, one bounded writer. Trigger evidence: mapper required reading 4+ files; implementation crosses multiple non-trivial files.
- TDD: strict test-first enabled by `openspec/config.yaml` (`sdd.strict_tdd: true`, `phase_rules.implementation.test_first: true`). Record RED/GREEN/refactor evidence; do not call the work SDD.
- Test runner: from `backend/`, `.venv/bin/python -m pytest tests/unit/test_analista_tecnico.py tests/unit/test_configuracion_normalizador_curricular.py -q`.
- Final implementation estimate: approximately 585 diff lines (tracked changes plus the 277-row source CSV, excluding the ODD tracker and unrelated existing changes). This exceeds the 400-line review slice budget. Delivery strategy: ask-on-risk before any future commit/PR; no commit requested or authorized.
- Current feature branch: `test/local-llm-technical-pipeline`; existing unrelated dirty files are out of scope.

## Verification

- Strict TDD RED/GREEN: six loader tests failed before implementation and passed after; config test failed on the old XLSX path before the setting changed.
- Focused analyzer/config suites after formatting: `41 passed`.
- Ruff check for all changed Python modules/tests: passed.
- LSP: both changed production Python modules clean; analyzer/config test files included one silent-clean-server inconclusive result in the batch.
- Scoped `git diff --check`: passed. Vendored CSV SHA-256 matches the user source (`126759c62272623a95f3652ab8139d034fe4b13b1ae66b241044110e4da33b84`).
- Scoped Git status confirms the CSV is untracked (not ignored); no claim about the unrelated worktree.

## Progress

- T1 and T2 implementation tasks complete. Production now loads all 277 official career-skill assignments, preserves all 222 source skill IDs, joins the existing descriptions, and documents that matching is strict rather than fuzzy.
- Native review was redirected to the user-authorized project root, but inspect reports 15 changed tracked paths plus a large untracked inventory. Several tracked paths are unrelated pre-existing changes, so starting would review the accumulated worktree rather than this feature slice. Stopped before untracked selection and START; no unrelated files were changed, moved, ignored, or registered, and no commit was made.
- ASSESS is unassessable because the candidate includes the unrelated worktree state; the independent verifier reran the 41 focused tests successfully.
- Engram mirror pending: local Engram server identity is unavailable in this session.
- Next: user decision whether to authorize review of the entire dirty worktree or leave native review blocked; no further native review action without that decision.
