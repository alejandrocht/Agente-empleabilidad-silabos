# Technical prompt weekly context and legacy cleanup

## Objective

Send extracted analytical-program rows to the active technical competency analyst and remove curriculum-only legacy analyzer, output, approval, and Neo4j compatibility seams that have no active callers.

## Tasks

- [x] Add the extracted week/topic/content rows to the technical LLM payload and prompt contract.
- [x] Refactor active technical approvals and Neo4j import to remove legacy imports and mode branches.
- [x] Delete legacy curriculum-only modules, scripts, and tests proven unreachable; update the deletion ledger and docs.
- [x] Run focused backend verification, static checks, and an import-safety audit; record failures and unavailable services.
- [x] Remove obsolete curricular presentation branches from the frontend while preserving employability CHH behavior and compatibility redirects.
- [x] Run the frontend test/build check and inspect the final technical-only diff.

## Constraints

- Preserve unrelated working-tree changes.
- Preserve employability CHH modules; remove only curriculum legacy seams.
- Keep evidence-backed technical proposals and approval gates unchanged.
- Do not send IDs, period, sumilla, declared competencies, tools, or graph relationships to the LLM.
- Keep the weekly context limited to extracted `semana`, `tema`, and `contenido` values.
- Do not commit or publish.

## Deletion ledger

Each deleted module/test was only referenced by the old curricular CHH analyzer/output/approval graph, legacy tests, or the retired profile bootstrap script. No active backend Python import remains after the technical approval exceptions and Neo4j compatibility loader were removed. Employability CHH modules under `backend/agente/normalizador/empleabilidad/` were preserved.

| Deleted surface | Evidence-based reason |
| --- | --- |
| `analista_llm.py`, `contexto_analista.py`, `contexto_curricular.py`, `normalizacion_decisiones.py`, `respuesta_cache_analista.py` | Historical semantic analyzer/cache; no production caller after technical routing. |
| `salida.py`, `normalizacion_curricular.py`, `release_gate.py`, `validacion_salida.py`, `resolucion_curricular.py`, `trazabilidad_curricular.py`, `integridad_chh.py` | Legacy CHH output/release/resolution tree; technical output is produced by `salida_catalogos.py`. |
| `aprobaciones.py`, `validacion_aprobaciones.py`, `transaccion_aprobaciones.py`, `mutaciones_aprobaciones.py`, `post_hitl_aprobaciones.py`, `presentacion_aprobaciones.py`, `persistencia_aprobaciones.py` | Retired curricular CHH approval transaction; technical journal is `aprobaciones_tecnicas.py`. |
| `clasificacion.py`, `paquetes.py`, `paquetes_componentes.py`, `paquetes_componentes_nombres.py`, `paquetes_relaciones.py`, `politica_curricular.py`, `herramientas.py` | Package/classification/tool helpers reachable only through the retired CHH path. |
| `perfil_carrera.py`, `perfiles.py`, `scripts/generar_perfil_carrera.py` | Profile bootstrap was an old CHH catalog workflow with no API/runtime caller. |
| `test_normalizador_analista_llm.py`, `test_normalizador_contexto_curricular.py`, `test_normalizador_embeddings.py`, `test_langsmith.py` | Tests for the deleted semantic analyzer, context, embeddings, and tracing path. |
| `test_normalizador_salida_contract.py`, `test_normalizador_computacion.py`, `test_normalizador_policy.py`, `test_normalizador_integridad_chh.py` | Tests for the deleted legacy output/release/resolution contract. |
| `test_normalizador_aprobaciones.py`, `test_normalizador_catalogo.py`, `test_normalizador_clasificacion.py`, `test_normalizador_herramientas.py`, `test_normalizador_paquetes.py`, `test_normalizador_paquetes_contract.py`, `test_technical_proposal_resilience.py` | Tests for the deleted CHH approval/package/catalog helpers. |

## Verification

- Focused technical/API/Neo4j suite: 75 passed.
- Full backend suite: 500 passed, 1 pre-existing unrelated failure in `tests/test_generated_query_contract.py` because the current Cypher model factory sends an extra `streaming=True` argument.
- AST import audit over `backend/agente`: passed with no imports of deleted curricular modules.
- `python -m compileall -q agente tests`: passed.
- Live Ollama/Neo4j smoke checks were not rerun; previous task evidence records both services unavailable.
- Frontend `npm run check`: 84 tests passed; Next.js webpack build passed. Historical `/dashborad` and nested inspection routes remain redirects; employability presentation and CSV previews remain active.
- Frontend curricular views now derive technical mode from `tipo === "silabos"`; old legacy CSV/report gates and `modo="legacy"` calls were removed from active presentation.
