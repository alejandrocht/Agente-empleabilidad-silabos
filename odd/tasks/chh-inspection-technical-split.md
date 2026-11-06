# CHH inspection and technical syllabus split

- [x] Map presentation branches and identify the `modoTecnico`/CHH entanglement.
- [x] Keep the three CHH catalog previews and nontechnical counts/title under `!esCurricular`.
- [x] Keep every `tipo: "silabos"` path on the technical five-CSV contract, technical approval/pending helpers, and `ALLOW_IMPORT` gate.
- [x] Remove only legacy curricular release-gate/output/Neo4j presentation branches.
- [x] Run focused and full frontend verification.

## Verification evidence

- `InspeccionEjecucionNormalizador.test.jsx`: 12 passed.
- Frontend `npm run check`: 85 tests passed and Next.js webpack build passed.
- Technical path still previews `curso.csv`, `silabo.csv`, `catalogo_competencias.csv`, `catalogo_logros.csv`, and `cobertura_curricular.csv` and only enables Neo4j through `ALLOW_IMPORT`.
- Employability path previews `catalogo_empleabilidad.csv`, `habilidades_empleabilidad.csv`, and `herramientas_empleabilidad.csv`; `requerimiento_laboral.csv` remains downloadable but is not treated as a catalog preview.
- Native review inspect stopped on `managed_assets_outdated`; the prescribed sync remains unavailable because no supported agent is selected, so no review lineage was created.
