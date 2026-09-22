# Rename competency description CSV column

## Objective

Expose the competency description column in `catalogo_competencias.csv` as `descripcion_breve` instead of `descripcion_breve_competencia`.

## Scope

- Change only the emitted five-file CSV contract for `catalogo_competencias.csv`.
- Preserve the internal analyzer proposal field `descripcion_breve_competencia`.
- Keep Neo4j import compatibility by translating the new CSV field to the existing graph property at the import boundary.
- Keep preview conflict comparison compatible by aliasing the existing graph property to the public CSV key.
- Update focused contract, importer, preview, and normalizer tests.
- Analyzer-input fixtures and docs may retain `descripcion_breve_competencia`; those are separate internal/legacy contracts, not the emitted CSV field.

## Tasks

- [x] T1. Add a regression asserting the exact `catalogo_competencias.csv` header uses `descripcion_breve`.
- [x] T2. Update CSV row materialization and Neo4j import translation without changing analyzer inputs.
- [x] T3. Run focused tests and static checks.
- [ ] T4. Commit only the scoped work on `test/local-llm-technical-pipeline`; push remains a user decision.

## Acceptance criteria

1. The generated header is `id_competencia,nombre_competencia,descripcion_breve,tipo_competencia,codigo_competencia`.
2. Every competency row retains its description under `descripcion_breve`.
3. Neo4j import still writes the existing `descripcion_breve_competencia` node property from the renamed CSV field.
4. Internal LLM/analyzer payloads remain unchanged.

## Allowed edit surfaces

- `backend/agente/normalizador/silabos/salida_catalogos.py`
- `backend/agente/db/neo4j_catalogos.py`
- `backend/agente/db/neo4j_importador.py`
- `backend/tests/unit/test_salida_catalogos.py`
- `backend/tests/unit/test_neo4j_catalogos.py`
- `backend/tests/unit/test_neo4j_importador.py`
- `backend/tests/unit/test_normalizador_silabos.py`
- `odd/tasks/rename-competency-description-column.md`

## Verification

- `cd backend && .venv/bin/python -m pytest tests/unit/test_salida_catalogos.py tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_silabos.py -q`
- `cd backend && .venv/bin/python -m ruff check agente/normalizador/silabos/salida_catalogos.py agente/db/neo4j_catalogos.py agente/db/neo4j_importador.py tests/unit/test_salida_catalogos.py tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_silabos.py`
- `cd backend && .venv/bin/python -m mypy agente/normalizador/silabos/salida_catalogos.py agente/db/neo4j_catalogos.py agente/db/neo4j_importador.py --show-error-codes --no-error-summary`
- Scoped `git diff --check`.

## Evidence

- RED (preview regression): same-ID/different-description preview was incorrectly importable because the graph property was returned under the legacy key without a public-schema alias.
- GREEN (preview regression): `cd backend && .venv/bin/python -m pytest tests/unit/test_neo4j_importador.py::test_preview_detects_legacy_description_conflict_using_public_alias -q` — 1 passed.
- Previous RED/GREEN evidence remains valid for the CSV writer/importer boundary; analyzer-input fixtures/docs retaining `descripcion_breve_competencia` were not renamed.
- Focused tests: `cd backend && .venv/bin/python -m pytest tests/unit/test_salida_catalogos.py tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_silabos.py -q` — 44 passed.
- Ruff: `cd backend && .venv/bin/python -m ruff check agente/normalizador/silabos/salida_catalogos.py agente/db/neo4j_catalogos.py agente/db/neo4j_importador.py tests/unit/test_salida_catalogos.py tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_silabos.py` — passed.
- Mypy: `cd backend && .venv/bin/python -m mypy agente/normalizador/silabos/salida_catalogos.py agente/db/neo4j_catalogos.py agente/db/neo4j_importador.py --show-error-codes --no-error-summary` — passed.
- Diff check: scoped `git diff --check` — passed.
- Independent verification: 44 focused tests passed; no remaining runtime consumer blocker.
- `backend/README.md` still shows the old output header, but it already contains unrelated local edits and is intentionally excluded from this scoped commit.
- Native review could not isolate this candidate from unrelated concurrent working-tree changes; no lineage was started. Independent verification passed.
