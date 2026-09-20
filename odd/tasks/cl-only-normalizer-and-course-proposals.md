# CL-only normalizer and course proposal presentation

- [x] Define the CL-only normalizer boundary and remove obsolete CHH/employability execution paths from it.
- [x] Include `nombre_curso` in technical proposal rows and show it in the approval UI instead of course/syllabus IDs.
- [x] Clean active CHH terminology and update focused contracts/tests.
- [x] Run focused and broader frontend/backend verification.

## Scope rule

The technical syllabus contract is the five mapped CSVs: `curso.csv`, `silabo.csv`, `catalogo_competencias.csv`, `catalogo_logros.csv`, and `cobertura_curricular.csv`. Proposal IDs remain internal decision keys; human-facing proposal cards show the course name. Generic graph query/schema surfaces are preserved unless they are part of the obsolete normalizer path.

## Verification

- Frontend: `npm run check` passed (68 tests and production build); focused approval/inspection tests passed (14 tests).
- Backend: focused curricular/technical suites passed (87 tests), Ruff and compileall passed; targeted mypy passed for `agente api`.
- Full `mypy .` remains blocked by the repository's duplicate module discovery for `auditoria_cypher_estructurada.py`.
- Native review was started for the existing high-tier workspace candidate but its provider collect bindings were rejected repeatedly; the user authorized `operator_disposition` abandonment, which committed quarantine without touching source files.
