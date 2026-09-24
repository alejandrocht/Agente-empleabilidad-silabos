# Log technical HITL switch changes

Status: committed locally; native review and authorized push pending
Repository: `Agente-empleabilidad-silabos`

## Goal

Emit a backend event immediately whenever the user toggles the technical HITL switch, without changing the existing execution-time HITL contract.

## Confirmed behavior

- `hitl=0` continues to run technical inference and automatically ADD valid pending proposals.
- `hitl=1` continues to leave proposals for manual review.
- Every explicit switch click sends `POST /api/normalizador/eventos/hitl` with `{ "hitl": 0|1 }`.
- The backend emits `normalizador.hitl_cambiado` with the selected mode and returns `204 No Content`; it does not create or mutate an execution.
- The selected value remains local and is sent again when the next execution starts.
- The existing normalizer router's loopback-only guard protects this endpoint.
- If the event request fails, keep the selected mode locally and show an accessible error; the next run still submits its mode.
- Programmatic reset to a new source is not a switch click and does not emit this event.

## Scope and non-goals

- Do not disable, skip, or alter technical inference.
- Do not change automatic approval, release-gate, execution persistence, or existing execution events.
- Do not log credentials, source data, or create an execution solely for a switch event.
- Do not modify the shared logger, server router registration, Next.js rewrite, or unrelated dirty files.
- No commit or push without a separate explicit user request.

## Confirmed test seams

1. Backend public HTTP seam: `POST /normalizador/eventos/hitl` validates the mode, emits the exact structured event, returns 204, rejects invalid values, and remains loopback-protected.
2. Frontend API seam: the helper sends the exact same-origin POST body and surfaces non-OK responses.
3. Frontend switch seam: each click calls the logging helper once with the next value; the selected value still reaches the next execution request; an event-log failure is accessible and does not silently revert the selection.

## Tasks

- [x] T1. Add the backend event endpoint and focused HTTP contract tests (test first). RED: 4 expected 404 failures; GREEN: 4 passed.
- [x] T2. Add the frontend API call, connect the switch handler, and test both success and log failure (test first). RED: API had 3 expected failures; panel had 2 expected failures. GREEN: combined 29 passed.
- [x] T3. Run focused backend/frontend tests, scoped lint/diff checks, and verify the existing inference/auto-ADD contract remains unchanged.

## Allowed code edit surfaces

- `backend/agente/api/normalizador.py`
- `backend/tests/unit/test_normalizador_hitl_evento.py` (new)
- `frontend/src/api/normalizador.js`
- `frontend/src/api/normalizador.test.js`
- `frontend/src/components/NormalizadorPanel.jsx`
- `frontend/src/components/NormalizadorPanel.test.jsx`

## Verification commands

- `cd Agente-empleabilidad-silabos/backend && python -m pytest tests/unit/test_normalizador_hitl_evento.py -q`
- `cd Agente-empleabilidad-silabos/frontend && npm test -- src/api/normalizador.test.js src/components/NormalizadorPanel.test.jsx`
- `cd Agente-empleabilidad-silabos/backend && ruff check agente/api/normalizador.py tests/unit/test_normalizador_hitl_evento.py`
- Scoped `git diff --check` for the six allowed code surfaces.

## Evidence

- The user authorized commit/push of exactly the seven listed paths; the parent inspected an empty staged area before staging only those seven paths.
- Confirmed by the user: preserve inference plus automatic ADD for `hitl=0`; emit a backend event on every explicit switch click.
- Agreed HTTP test seam: `POST /api/normalizador/eventos/hitl` → `normalizador.hitl_cambiado` → 204, without creating an execution.
- `log_paso` accepts an empty session ID and sanitizes data; no logger change is needed.
- The frontend rewrite maps `/api/normalizador/:path*` to the backend's `/normalizador/:path*` route.
- The backend registers the normalizer router with the existing loopback-only administrative dependency.
- T1 exact focused command passed: `cd Agente-empleabilidad-silabos/backend && python -m pytest tests/unit/test_normalizador_hitl_evento.py -q` — 4 passed (1.86s); scoped `git diff --check` passed.
- Pi Lens reported automatic formatting of the dedicated test outside turn; the parent reread the test file and the focused suite passed again (4/4).
- T2 API RED: `npm test -- src/api/normalizador.test.js` — 4/7 passed before implementation. Panel RED: `npm test -- src/components/NormalizadorPanel.test.jsx` — 20/22 passed before implementation. Combined GREEN: `npm test -- src/api/normalizador.test.js src/components/NormalizadorPanel.test.jsx` — 29/29 passed.
- Independent verification: frontend focused suite 29/29; backend Ruff `All checks passed!`; scoped tracked `git diff --check` clean. Backend focused HTTP suite passed 4/4 twice, including invalid-mode and remote-peer coverage.
- The next-run payload remains the selected `hitl` value (existing Cactus test verifies `hitl=0`); no inference or auto-ADD implementation was changed.
- Native ASSESS returned `unassessable` because an unrelated untracked worktrees directory was present; it prescribed independent verification, which completed successfully.
- Engram mirror is unavailable in this session. Commit `dee7c85` (`feat(normalizer): log HITL switch changes`) was created locally for exactly this seven-path slice; native review and authorized push remain pending.
- Latest authorized frontend regression asserts exactly one logging call per click and verifies that after logging failure, the next Cactus run still submits `hitl=0`.
- Latest verification: backend focused HTTP suite — 4 passed; scoped Ruff — all checks passed; frontend API+panel suite — 29 passed across 2 files; scoped `git diff --check` — clean.
- LSP error scan found 0 diagnostics. Three frontend LSP results remain unconfirmed because the server did not publish on clean re-check; the frontend tests passed.
