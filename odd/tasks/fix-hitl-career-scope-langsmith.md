# Fix HITL career scope and LangSmith telemetry

## Objective

Prevent final technical proposal decisions from failing when the user-facing career label differs from the canonical value stored in cleaned syllabus records, and keep invalid LangSmith telemetry configuration from polluting or blocking the workflow.

## Scope

- Use the validated canonical career/period when rematerializing technical outputs after HITL decisions.
- Preserve strict rejection of genuinely mixed career/period batches.
- Return a domain validation response instead of leaking output-contract `ValueError` as HTTP 500.
- Disable LangSmith tracing unless it is explicitly enabled and an API key is configured.
- Add focused backend regression tests.
- Do not touch the parallel analyst/deduplication surfaces: `backend/agente/normalizador/silabos/analista_tecnico.py` and `backend/tests/unit/test_analista_tecnico.py`.

## Tasks

- [x] Add regression tests for canonical career scope, mixed batches, and tracing configuration.
- [x] Fix post-HITL materialization scope and domain error translation.
- [x] Make LangSmith tracing opt-in only with credentials.
- [x] Run focused verification and inspect the diff.

## Evidence

- Reproduction: posting `ADD` to `/normalizador/ejecuciones/{id}/pendientes/decidir` after adding a canonical/other-career record returned HTTP 500 with `ValueError: El lote mezcla carreras`.
- Root cause: `aprobaciones_tecnicas._materializar` passed raw `manifest.parametros` into `construir_salidas_tecnicas`, while `validar_archivo` canonicalizes career labels before writing cleaned records.
- LangSmith 401 is asynchronous exporter telemetry; `LANGSMITH_TRACING` can enable tracing without a nonempty `LANGSMITH_API_KEY`.

## Progress/Verification

- Canonical validated career/period scope is used.
- Legacy manifests normalize parameters.
- Mixed batches return HTTP 422 with rollback.
- LangSmith tracing requires explicit enablement plus a nonempty API key.
- Focused tests: 15 passed.
- `compileall` passed.
- `git diff --check` passed.
- Broader suite has one pre-existing timing failure in `test_normalizador_api.py::test_inicia_y_consulta_ejecucion_de_silabos`.
- No commit was created.

## Delivery

No commit or push without explicit user authorization.
