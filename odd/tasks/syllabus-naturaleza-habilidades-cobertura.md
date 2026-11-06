# Syllabus nature and skills coverage output

## Goal
Update the syllabus normalizer and Neo4j catalog importer to extract `tipo_curso` from “Tipo de asignatura”, extract a separate `naturaleza` field, stop extracting “Modalidad”, publish approved technical skills as `Habilidad` rows in a new CSV, and route curricular links through `CoberturaCurricular` using the confirmed screenshot contract.

## Confirmed contract
- `curso.csv` has separate `tipo_curso` and `naturaleza` columns. Source rows are “Tipo de asignatura” and “Naturaleza”, respectively. `naturaleza` belongs to `Curso`, not `Silabo`; do not extract “Modalidad”.
- Only approved technical competencies become `Habilidad`; declared generic/specific competencies remain `Competencia`.
- Official source IDs currently use `COMP_TEC_####`; transform only that prefix to `HAB_TEC_####` in the published output, preserving the four digits. Identical technical skills intentionally reuse one global ID across careers: `id_habilidad` is the Habilidad identity, while each `CoberturaCurricular` associates it with its course/syllabus. `id_carrera` remains in the per-career CSV row but is not a skill identity key. Never synthesize an ID for an approved skill without a matching catalog reference; fail closed with a clear validation error.
- Add `catalogo_habilidades.csv` with `id_habilidad,id_carrera,nombre_habilidad,desc_breve`.
- `cobertura_curricular.csv` uses `id_cobertura_curricular,id_curso,id_silabo,id_competencia,id_habilidad,id_logro`.
- Use the screenshot relationship names `CUBRE_COMPETENCIA`, `CUBRE_HABILIDAD`, `CUBRE_LOGRO`. Remove direct Curso–Silabo links; connect both to CoberturaCurricular. Preserve Carrera–Curso behavior and do not create a separate Carrera–Habilidad relationship.
- Do not connect to a live Neo4j database or mutate existing graph data during verification.


## Tasks
- [x] Change DOCX/PDF extraction and course CSV schema for the two separate syllabus rows; add regression tests.
- [x] Materialize approved technical skills into `catalogo_habilidades.csv` and the new coverage schema; validate IDs and write unit tests.
- [x] Update Neo4j CSV validation/import, public output filtering, API/output assertions, and the README schema while preserving pre-existing user edits. Treat repeated `HAB_TEC_####` values as the same global skill; career-specific use is expressed through CoberturaCurricular, not a different skill ID.
- [x] Run focused backend tests and inspect actual temporary CSV headers/rows; record exact results.
- [ ] Create and natively review feature-only work-unit commits on `test/local-llm-technical-pipeline`; preserve every unrelated dirty change.

## TDD and verification
- Strict TDD: active from the installed `gentle-ai` skill; source: `/Users/alejandromcht/.pi/agent/git/github.com/Gentleman-Programming/gentle-pi/skills/gentle-ai/SKILL.md`.
- Runner: `python -m pytest` from `backend`.
- Required command: `cd Agente-empleabilidad-silabos/backend && python -m pytest tests/unit/test_normalizador_silabos.py tests/unit/test_salida_catalogos.py tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py tests/unit/test_normalizador_api.py tests/unit/test_normalizador_ejecuciones.py tests/unit/test_post_hitl_workflow.py -q` — **98 passed**.
- A temporary-output inspection asserted exact headers and rows for `curso.csv`, `catalogo_habilidades.csv`, and `cobertura_curricular.csv`, including `Obligatorio`, `Taller`, and `HAB_TEC_0007`; it passed without writing to repository output folders.

## Constraints and boundaries
- Target worktree: `Agente-empleabilidad-silabos`, branch `test/local-llm-technical-pipeline`.
- Preserve all pre-existing modified/untracked files; in particular do not rewrite the existing edits in `backend/README.md`, `backend/agente/normalizador/silabos/analista_tecnico.py`, `backend/tests/unit/test_normalizador_ejecuciones.py`, or the untracked career/skill catalog.
- Do not modify the official CSV under Desktop or its project copy.
- Do not run migrations or import into a live Neo4j database. The user explicitly authorized feature-only work-unit commits and directly requested pushing commit `8e619e1` to `origin/test/local-llm-technical-pipeline` despite the native review not running; do not include unrelated dirty hunks.

## Evidence
- Initial source map and screenshot contract were reviewed before writing.
- Strict-TDD implementation and regressions passed; the focused importer regression first reproduced `KeyError: 'nuevas_habilidades'`, then passed after the counter fix. Shared cross-career Habilidad identity also has writer/preview regression tests.
- The official catalog contains `COMP_TEC_0007` under two career IDs with identical skill content. User clarified that same content intentionally shares one global ID and all course/syllabus/skill relations flow through CoberturaCurricular; the supplied graph page confirms the bridge-node pattern. `naturaleza` is on Curso, not Silabo.
- Final exact focused suite: 98 passed. Temporary CSV inspection verified the exact course, skill, and coverage headers and representative emitted values in a temporary directory.
- Native review inspect/start stopped before authority creation with `lens_context_budget_exceeded` because the complete dirty tracked workspace exceeds the reviewer budget. No review approval or native authority was created; isolate this feature in smaller committed ranges.
- Slice 1 commit: `8e619e19e9f0e479412fc9767076b0a04a3d5ef4` (`feat(syllabus): add skill coverage CSVs`). Remaining slices are not committed yet.
- The initial committed-range START was rejected with `candidate-target-projection-drift` before lineage creation or mutation because inspect had bound the dirty workspace; an isolated worktree was then used for the exact commit patch.
- Isolated native START returned `consent-declined-this-candidate` with `lineage_created:false`; no review ran. Do not retry this candidate. No additional feature commits were made.
- User explicitly requested pushing slice 1; `8e619e1` was pushed to `origin/test/local-llm-technical-pipeline` (`bcff206..8e619e1`). Native review remains unresolved and the remaining feature changes are uncommitted.
- Existing checkout has unrelated dirty changes; preserve them. A concurrent session confirmed ownership of the frontend HITL/navigation/progress diffs; they are outside this task and remain untouched.
