# Apply Progress: Harden Normalizer Reliability

## Session and status

- Change: `harden-normalizer-reliability`
- Phase: `sdd-apply`
- Native status consumed: `gentle-ai.sdd-status` v2, `applyState=ready`, `nextRecommended=apply`, task progress `0/8` before this slice.
- Action context: `repo-local`; workspace root and allowed edit root are the canonical repository.
- Action warnings: none; external services were forbidden and none were invoked.
- Assigned delivery boundary: U1 only, candidate PR 1, `auto-chain`, stacked-to-main, 400-line review budget.

## Completed task

- [x] U1 — Protect administrative routes with one direct-loopback seam. The persisted checkbox was updated from `[ ]` to `[x]` in `tasks.md` immediately after verification.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| U1 | `tests/unit/test_normalizador_api.py`, `tests/unit/test_neo4j_importacion_api.py` | FastAPI/TestClient + unit | ✅ 94 passed | ✅ Focused collection failed before production: `ModuleNotFoundError: No module named 'agente.api.acceso_administrativo'` (exit 2) | ✅ Focused suite: `97 passed in 2.74s` after guard and router wiring | ✅ `2 passed in 1.83s`; covers malformed/DNS/private/public/mapped peers and public routes from a non-loopback peer | ✅ Final focused suite: `99 passed in 2.62s`; targeted Ruff passed; docs and explicit TestClient peers updated |

### Exact commands and outcomes

1. Safety-net baseline:
   - Command: `cd backend && python -m pytest -q tests/unit/test_normalizador_api.py tests/unit/test_neo4j_importacion_api.py tests/unit/test_normalizador_ejecuciones.py tests/unit/test_normalizador_aprobaciones.py`
   - Result: `94 passed in 3.09s`
2. RED:
   - Same focused command after writing behavior tests first.
   - Result: collection failed with `ModuleNotFoundError: No module named 'agente.api.acceso_administrativo'`, exit code `2`.
3. GREEN:
   - Same focused command after the minimum guard and router dependency wiring, with existing administrative clients made explicit loopback peers.
   - Result: `97 passed in 2.74s`.
4. TRIANGULATE:
   - Command: `cd backend && python -m pytest -q tests/unit/test_normalizador_api.py::test_guardia_rechaza_formas_no_loopback_y_no_resuelve_nombres tests/unit/test_normalizador_api.py::test_rutas_publicas_conservan_acceso_desde_peer_remoto`
   - Result: `2 passed in 1.83s`.
5. REFACTOR/final U1 verification:
   - Command: `cd backend && python -m pytest -q tests/unit/test_normalizador_api.py tests/unit/test_neo4j_importacion_api.py tests/unit/test_normalizador_ejecuciones.py tests/unit/test_normalizador_aprobaciones.py`
   - Result: `99 passed in 2.62s`.
   - Command: `cd backend && python -m ruff check agente/api/servidor.py agente/api/acceso_administrativo.py api/servidor.py`
   - Result: `All checks passed!`

## Implementation evidence

- Added `backend/agente/api/acceso_administrativo.py` with `ipaddress.ip_address`, direct-peer-only validation, loopback IPv4/IPv6 and mapped-loopback handling, generic 403, and no forwarded-header/auth bypass.
- Updated `backend/api/servidor.py` to attach the same replaceable dependency only while including `/normalizador` and `/neo4j` routers.
- Updated allowed administrative tests to use explicit `client=("127.0.0.1", 0)` and added remote-peer/header rejection and public-route preservation coverage.
- Updated `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md` with the loopback-only replacement point and unsupported reverse-proxy/multi-process limitation.
- The curricular analyst prompt and all U2-U8 production surfaces were untouched.

## Deviations and blockers

- No design deviations.
- The editor's background diagnostics reported stale/misattributed pre-existing typing/import warnings, but the exact targeted Ruff command and focused runtime suite passed. No unrelated diagnostics were changed.
- No live LLM, Neo4j, LangSmith, Cactus/browser, network, paid API, or production service was used.

## Remaining implementation tasks

- [ ] U2 — Reject oversized uploads before history allocation and during bounded streaming. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U3 — Reconcile stale non-terminal executions at single-instance startup. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U4 — Preserve one private stable syllabus source through finalization. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U5 — Make HITL snapshot, mutation, and rollback one locked transaction. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U6 — Aggregate curricular LLM failures into an explicit publication blocker. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U7 — Reconcile Neo4j graph commits with durable local import history. Implement and verify the behavior. <!-- sdd-owner: implementation -->
- [ ] U8 — Make relationship rollback ownership- and dependency-safe. Implement and verify the behavior. <!-- sdd-owner: implementation -->

## Next recommendation

U1 is complete within the assigned candidate PR 1 boundary. Remaining work proceeds through the parent/orchestrator as U2-U8; this slice recommends `sdd-verify` only after all implementation tasks are complete.

    ## U1 budget-split addendum

    - U1 behavior remains complete and unchanged. Only the U1-authored documentation hunks were removed from `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md`; U1 documentation is explicitly deferred to the later U2–U4 lifecycle/docs review slice and is not currently landed.

- Both `backend/README.md` and `docs/DOCUMENTACION_TECNICA_CIAR.md` now have zero Git diff; all U1-era documentation and formatter hunks were removed. No source or test file was edited in this follow-up.
- Verification was run after documentation removal, exactly as requested:
      1. `cd backend && python -m pytest -q tests/unit/test_normalizador_api.py tests/unit/test_neo4j_importacion_api.py tests/unit/test_normalizador_ejecuciones.py tests/unit/test_normalizador_aprobaciones.py` — `99 passed in 2.56s`.
      2. `cd backend && python -m ruff check agente/api/servidor.py agente/api/acceso_administrativo.py api/servidor.py` — `All checks passed!`.
      3. `cd backend && python -m compileall -q agente api scripts && echo compileall-pass` — `compileall-pass`.
- Current U1 review-slice arithmetic excludes `.atl/*`, `.gitignore`, intended OpenSpec planning/tool state, `apply-progress.md`, and both documentation paths, which are now clean. Exact command: `git diff --numstat -- backend/api/servidor.py backend/tests/unit/test_neo4j_importacion_api.py backend/tests/unit/test_normalizador_api.py backend/tests/unit/test_normalizador_aprobaciones.py backend/tests/unit/test_normalizador_ejecuciones.py`; its rows total `175 additions + 72 deletions = 247`. Add `backend/agente/api/acceso_administrativo.py` (`29 + 0 = 29`) and the one-line U1 budget-split note in `tasks.md` (`1 + 0 = 1`): `205 additions + 72 deletions = 277 changed lines`, which is `277 <= 400`.
- Persisted task status remains U1 `[x]`; U2, U3, U4, U5, U6, U7, and U8 remain `[ ]`. The prior TDD evidence above is preserved; this documentation-only budget split adds no new production/test TDD cycle.

## U1 budget-split correction evidence

- Gatekeeper correction accepted: the pre-U1 baseline for both documentation paths was clean, so no documentation diff is treated as pre-existing or retained.
- Hard gate: `git diff --quiet -- backend/README.md docs/DOCUMENTACION_TECNICA_CIAR.md` exited `0` after restoring both files byte-for-byte from Git HEAD.
- The original U1 TDD evidence remains unchanged above; this correction only removes documentation drift and corrects its progress accounting.

## U2a — Early trustworthy request-length rejection

- Native status consumed: `gentle-ai.sdd-status` v2, `applyState=ready`, `nextRecommended=apply`; active attempt acquired at expected revision `sha256:4530c3b71746618aa2252eaa38ec1a4d3b0377729bc6e19e262ace54e68c01b2`, work unit `U2a-early-request-limit`, token retained for settle.
- Action context: `repo-local`; only the canonical workspace is writable. The exact selected untracked paths were `openspec/changes/harden-normalizer-reliability/tasks.md` and `openspec/changes/harden-normalizer-reliability/apply-progress.md`; all other untracked paths were excluded.
- Scope boundary: only early rejection when a valid decimal `Content-Length` proves the request exceeds `MAX_UPLOAD_BYTES` for `/normalizador/empleabilidad` and `/normalizador/silabos`. No bounded streaming, scratch staging, ZIP checks, docs/config, U2b, U3, or U4 behavior was implemented.

### U2a TDD Cycle Evidence

| Cycle | Exact command | Evidence |
| ------ | --------------- | ---------- |
| RED | `cd backend && python -m pytest -q tests/unit/test_normalizador_api.py::test_rechaza_content_length_excesivo_antes_de_crear_ejecucion` | `2 failed`; both cases reached `gestor_ejecuciones.crear` and raised `AssertionError: crear no debe ejecutarse antes del rechazo`. |
| GREEN | Same focused command | `2 passed in 1.83s`; both routes returned `413`, generic detail, zero `crear` calls, and no temporary execution directory. |
| TRIANGULATE | `cd backend && python -m pytest -q tests/unit/test_normalizador_api.py` | `16 passed in 1.91s`; existing accepted upload behavior remained `202`. |
| REFACTOR / quality | `cd backend && python -m ruff check agente/api/normalizador.py tests/unit/test_normalizador_api.py` | `All checks passed!`; `cd backend && python -m compileall -q agente api scripts && echo compileall-pass` returned `compileall-pass`; path-scoped `git diff --check` passed. |

- Files changed in this sub-slice: `backend/agente/api/normalizador.py`, `backend/tests/unit/test_normalizador_api.py`, and the two permitted OpenSpec progress artifacts. No other path was edited by this work unit.
- Review accounting against the acquired U2a candidate baseline: production/test source delta is `48 additions + 6 deletions` in `normalizador.py` and `79 additions + 16 deletions` in `test_normalizador_api.py`, for `127 additions + 22 deletions = 149 changed lines`, within the explicit 160-line attempt cap and the 400-line review budget. The selected untracked task/progress artifacts are baseline artifacts and excluded from authored source accounting.
- Persisted task status: U1 remains `[x]`; U2, U3, U4, U5, U6, U7, and U8 remain `[ ]`. U2a evidence is recorded as a sub-slice and does not complete U2.
- Remaining tasks are the exact unchecked lines for U2 through U8 in `tasks.md`; U2's remaining bounded-streaming, scratch cleanup, ZIP preflight, and documentation work is not part of this attempt.
