# T5: Neutral technical exceptions and legacy import cleanup

- [x] Confirm the active syllabus path and map startup imports/callers.
- [x] Move the three approval exception classes into `silabos/errores_tecnicos.py`; update API and tests.
- [x] Verify/remove any remaining legacy startup imports and dead Neo4j legacy surfaces.
- [x] Run focused import-safety and backend verification; record unrelated failures.

## Acceptance criteria

- Importing the active normalizer/API does not import `validacion_aprobaciones`, legacy approval facades, legacy catalog output, or package helper modules.
- `aprobaciones_tecnicas.py` resolves exceptions from `agente.normalizador.silabos.errores_tecnicos` and technical output code only.
- Public Neo4j preview/import paths use only `_cargar_fuente_tecnica` and `_escribir_grafo_tecnico`; no `_cargar_salida_legacy` remains.
- Existing technical approval behavior and HTTP error mapping remain unchanged.

## Verification evidence

- Focused backend tests: 35 passed (`test_neo4j_importador.py`, `test_normalizador_ejecuciones.py`, `test_normalizador_api.py`).
- Backend Ruff, mypy, focused 19-test regression, neutral identity smoke, LSP diagnostics, and diff checks passed.
- Active-source AST audit found no imports of deleted legacy approval/catalog/package modules; `perfiles.py` and `generar_perfil_carrera.py` remain absent.
- Full backend suite: 500 passed, 1 unrelated failure in `tests/test_generated_query_contract.py` because the model factory supplies `streaming=True` while the fixture expects four kwargs.
- Native review inspect stopped on `managed_assets_outdated`; the prescribed sync was attempted but could not run because no supported agent was selected, so no review lineage was created.
